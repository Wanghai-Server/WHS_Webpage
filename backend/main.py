import asyncio
import base64
import hashlib
import hmac
import json
import re
import secrets
import smtplib
import sys
import time
import urllib.parse
import urllib.request
import uuid
from contextlib import asynccontextmanager
from email.message import EmailMessage
from pathlib import Path

from fastapi import Body, Depends, FastAPI, File, Form, Header, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

# 将项目根目录加入 sys.path，以便导入与 backend/ 同级的 data 包。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data import read_config, read_whs_config
from data.exam import ExamConfigError, load_exam_config
from data.main.database.exam_database import ExamDatabase
from data.main.database.message_database import MessageDatabase
from data.main.database.user_database import (
    ERROR_MESSAGES as USER_DB_ERROR_MESSAGES,
    UserDatabase,
    UserDatabaseError,
    UserInfoDatabase,
    UserNotFoundError,
)

# 用户数据库实例：随服务启动连接、随服务关闭释放。
user_db = UserDatabase()
user_info_db = UserInfoDatabase()
message_db = MessageDatabase()
exam_db = ExamDatabase()

# 头像存储目录、大小上限、允许的 MIME 类型。
AVATAR_DIR = PROJECT_ROOT / "data" / "avatar"
MAX_AVATAR_SIZE = 2 * 1024 * 1024  # 2MB
AVATAR_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
}

# 考试附件（图片）存储目录、大小上限、允许的 MIME 类型。
EXAM_UPLOAD_DIR = PROJECT_ROOT / "data" / "exam_upload"
MAX_EXAM_UPLOAD_SIZE = 5 * 1024 * 1024  # 5MB
EXAM_UPLOAD_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

# 与数据层一致：邮箱 / 密码格式。
# 三段式邮箱：本地部分 + 单个@ + 域名(至少一个点)。
EMAIL_RE = re.compile(r"[a-zA-Z0-9_.-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+")
PASSWORD_RE = re.compile(r"^[\x00-\x7f]+$")
USERNAME_RE = re.compile(r"[a-zA-Z0-9_]+")

# 邮箱验证码：内存存储 email -> {code, exp}，TTL 5 分钟。
VERIFY_CODES = {}
CODE_TTL = 300

# 同一邮箱发送验证码的冷却时间（秒）。
SEND_COOLDOWN = 60
_last_send_time: dict[str, float] = {}

# 连续输错密码 / 验证码次数上限，达到即锁定账号。
MAX_FAILURES = 5
_login_failures: dict[str, dict[str, int]] = {}


def _config() -> dict:
    return read_config()


def _token_secret() -> str:
    return _config().get("token_secret") or "whs_dev_secret"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def create_token(uid: int, ttl: int = 7 * 24 * 3600) -> str:
    """签发一个轻量 HMAC-SHA256 令牌（JWT 风格，无第三方依赖）。"""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"uid": uid, "exp": int(time.time()) + ttl}
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(_token_secret().encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url(sig)}"


def verify_token(token: str) -> dict | None:
    """校验令牌，有效则返回 payload，否则返回 None。"""
    try:
        h, p, s = token.split(".")
        expected = hmac.new(_token_secret().encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url(expected), s):
            return None
        payload = json.loads(_b64url_decode(p))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def _hash_password(client_hash: str) -> str:
    """给前端传来的 sha256 哈希加盐，返回 "<salt>$<salted_hash>"。"""
    salt = secrets.token_hex(16)
    final = hashlib.sha256(f"{salt}{client_hash}".encode()).hexdigest()
    return f"{salt}${final}"


def _verify_password(stored: str, client_hash: str) -> bool:
    """校验加盐后的密码。stored 形如 "<salt>$<hash>"。"""
    try:
        salt, expected = stored.split("$", 1)
    except ValueError:
        return False
    actual = hashlib.sha256(f"{salt}{client_hash}".encode()).hexdigest()
    return hmac.compare_digest(actual, expected)


def _public_user(user: dict) -> dict:
    """去除 password 哈希，只返回可对外暴露的字段。"""
    return {k: v for k, v in user.items() if k != "password"}


def _derive_username(email: str) -> str:
    """由邮箱自动生成一个满足 [a-zA-Z0-9_]+ 且唯一的 username。"""
    base = re.sub(r"[^a-zA-Z0-9_]", "", email.split("@")[0]) or "user"
    candidate = base
    while user_db.get_user(username=candidate) is not None:
        candidate = f"{base}_{uuid.uuid4().hex[:6]}"
    return candidate


def _find_by_identifier(identifier: str):
    """按 email / UID / username 查找用户。"""
    if not identifier:
        return None
    if identifier.isdigit():
        u = user_db.get_user(uid=int(identifier))
        if u:
            return u
    if EMAIL_RE.fullmatch(identifier):
        u = user_db.get_user(email=identifier)
        if u:
            return u
    return user_db.get_user(username=identifier)


def get_current_user(authorization: str = Header(None)):
    """FastAPI 依赖：从 Authorization: Bearer <token> 解析当前登录用户；未登录返回 None。"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    payload = verify_token(authorization[7:])
    if payload is None:
        return None
    user = user_db.get_user(uid=payload.get("uid"))
    # 被封禁用户的 token 视为失效（等同于登出）
    if user is None or user.get("banned"):
        return None
    return user


def _verify_hcaptcha_sync(response: str) -> bool:
    secret = _config().get("hcaptcha", {}).get("secret_key", "")
    if not secret or not response:
        return False
    data = urllib.parse.urlencode({"secret": secret, "response": response}).encode()
    req = urllib.request.Request("https://api.hcaptcha.com/siteverify", data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
        return bool(result.get("success"))
    except Exception as exc:
        print(f"[hcaptcha] siteverify 请求失败: {type(exc).__name__}: {exc}", flush=True)
        return False


async def _verify_hcaptcha(response: str) -> bool:
    return await asyncio.to_thread(_verify_hcaptcha_sync, response)


def _send_email(to: str, subject: str, body: str, locale: str = "zh") -> bool:
    """通过 SMTP 发送邮件；失败返回 False（不抛异常，由调用方降级处理）。"""
    try:
        smtp_public = read_whs_config().get("smtp", {})
        smtp_private = read_config().get("smtp", {})
        host = smtp_public.get("host") or "localhost"
        port = int(smtp_public.get("port") or 2000)
        sender_email = smtp_public.get("sender") or smtp_private.get("username") or "noreply@localhost"
        sender_name_map = smtp_public.get("sender_name") or {}
        sender_name = sender_name_map.get(locale) or sender_name_map.get("zh") or ""
        sender = f"{sender_name} <{sender_email}>" if sender_name else sender_email
        username = smtp_private.get("username") or ""
        password = smtp_private.get("password") or ""
        use_ssl = bool(smtp_public.get("use_ssl", False))

        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)

        server_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with server_cls(host, port, timeout=10) as server:
            if username:
                server.login(username, password)
            server.send_message(msg)
        return True
    except Exception as exc:
        print(f"[smtp] 发送失败: {type(exc).__name__}: {exc}", flush=True)
        return False


def _record_failure(uid: int, kind: str) -> bool:
    """记录一次登录失败；达到 MAX_FAILURES 则锁定账号并返回 True。"""
    key = str(uid)
    entry = _login_failures.setdefault(key, {"password": 0, "code": 0})
    entry[kind] += 1
    if entry[kind] >= MAX_FAILURES:
        user_db.set_locked(uid, True)
        entry[kind] = 0
        return True
    return False


def _clear_failures(uid: int) -> None:
    """登录成功后清零该账号的失败计数。"""
    _login_failures.pop(str(uid), None)


# 汇总双语错误消息（数据库错误 + 后端错误）。
ERROR_MESSAGES = {
    **USER_DB_ERROR_MESSAGES,
    "avatar_too_large": {
        "zh": "头像大小不能超过 2MB",
        "en": "Avatar must not exceed 2MB",
    },
    "avatar_unsupported_type": {
        "zh": "头像仅支持 jpg / png / webp / ico",
        "en": "Avatar must be jpg, png, webp or ico",
    },
    "avatar_not_found": {
        "zh": "头像不存在",
        "en": "Avatar not found",
    },
    "code_invalid": {
        "zh": "验证码错误或已过期",
        "en": "Verification code is invalid or expired",
    },
    "captcha_invalid": {
        "zh": "人机验证未通过",
        "en": "Captcha verification failed",
    },
    "invalid_credentials": {
        "zh": "账号或密码错误",
        "en": "Invalid credentials",
    },
    "unauthorized": {
        "zh": "未登录或登录已过期",
        "en": "Unauthorized",
    },
    "send_code_too_frequent": {
        "zh": "验证码发送过于频繁，请稍后再试",
        "en": "Verification code sent too frequently, please try again later",
    },
    "email_send_failed": {
        "zh": "验证码邮件发送失败，请稍后再试",
        "en": "Failed to send the verification email, please try again later",
    },
    "account_locked": {
        "zh": "账号已被锁定，请联系管理员解锁",
        "en": "Account locked, please contact an administrator to unlock",
    },
    "permission_denied": {
        "zh": "权限不足",
        "en": "Permission denied",
    },
    "gender_invalid": {
        "zh": "性别选项不合法",
        "en": "Invalid gender option",
    },
    "birthday_invalid": {
        "zh": "生日格式不合法",
        "en": "Invalid birthday",
    },
    "account_banned": {
        "zh": "账号已被封禁，请联系管理员",
        "en": "Account banned, please contact an administrator",
    },
    "cannot_follow_self": {
        "zh": "不能关注自己",
        "en": "You cannot follow yourself",
    },
    "old_password_invalid": {
        "zh": "旧密码错误",
        "en": "Current password is incorrect",
    },
    "invalid_permission": {
        "zh": "权限值不合法（0~4 的整数）",
        "en": "Invalid permission value (integer 0-4)",
    },
    "cannot_ban_self": {
        "zh": "不能封禁自己",
        "en": "You cannot ban yourself",
    },
    "cannot_change_own_permission": {
        "zh": "不能修改自己的权限",
        "en": "You cannot change your own permission",
    },
    "cannot_modify_higher_permission": {
        "zh": "不能操作权限不低于自己的用户",
        "en": "You cannot manage users with permission equal or higher than yours",
    },
    "email_same": {
        "zh": "新邮箱不能与当前邮箱相同",
        "en": "New email must be different from the current one",
    },
    "message_content_empty": {
        "zh": "消息内容不能为空",
        "en": "Message content cannot be empty",
    },
    "message_title_empty": {
        "zh": "消息标题不能为空",
        "en": "Message title cannot be empty",
    },
    "exam_config_error": {
        "zh": "考试配置错误，请联系管理员",
        "en": "Exam config error, please contact an administrator",
    },
    "exam_question_not_found": {
        "zh": "题目不存在",
        "en": "Question not found",
    },
    "exam_answer_invalid": {
        "zh": "答案格式不合法",
        "en": "Invalid answer format",
    },
    "exam_upload_not_allowed": {
        "zh": "该题不允许上传附件",
        "en": "Upload not allowed for this question",
    },
    "exam_upload_unsupported": {
        "zh": "仅支持上传图片（jpg/png/webp/gif）",
        "en": "Only jpg/png/webp/gif images are supported",
    },
    "exam_upload_too_large": {
        "zh": "附件大小不能超过 5MB",
        "en": "Attachment must not exceed 5MB",
    },
    "exam_not_finished": {
        "zh": "还有题目未作答，请完成全部题目",
        "en": "Some questions are not answered yet",
    },
    "exam_attempts_exhausted": {
        "zh": "答题次数已用完，无法再次作答",
        "en": "You have exhausted your attempts",
    },
    "exam_cannot_answer": {
        "zh": "当前不允许答题（次数已用完或已通过）",
        "en": "Not allowed to take the exam now",
    },
    "exam_profile_incomplete": {
        "zh": "请先完善个人信息",
        "en": "Please complete your profile first",
    },
    "exam_answers_not_found": {
        "zh": "该用户暂无答卷",
        "en": "No answer sheet found for this user",
    },
    "exam_score_invalid": {
        "zh": "分数不合法",
        "en": "Invalid score",
    },
    "exam_attachment_not_found": {
        "zh": "附件不存在",
        "en": "Attachment not found",
    },
    "message_not_found": {
        "zh": "消息不存在",
        "en": "Message not found",
    },
}

# 错误码 -> HTTP 状态码。
ERROR_STATUS: dict[str, int] = {
    "username_invalid": 400,
    "player_name_invalid": 400,
    "email_invalid": 400,
    "password_invalid": 400,
    "username_exists": 409,
    "email_exists": 409,
    "player_name_exists": 409,
    "user_not_found": 404,
    "avatar_too_large": 413,
    "avatar_unsupported_type": 400,
    "avatar_not_found": 404,
    "code_invalid": 400,
    "captcha_invalid": 400,
    "invalid_credentials": 401,
    "unauthorized": 401,
    "send_code_too_frequent": 429,
    "email_send_failed": 502,
    "account_locked": 403,
    "permission_denied": 403,
    "gender_invalid": 400,
    "birthday_invalid": 400,
    "account_banned": 403,
    "cannot_follow_self": 400,
    "old_password_invalid": 400,
    "invalid_permission": 400,
    "cannot_ban_self": 400,
    "cannot_change_own_permission": 400,
    "cannot_modify_higher_permission": 403,
    "email_same": 400,
    "message_content_empty": 400,
    "message_title_empty": 400,
    "message_not_found": 404,
    "exam_config_error": 500,
    "exam_question_not_found": 404,
    "exam_answer_invalid": 400,
    "exam_upload_not_allowed": 400,
    "exam_upload_unsupported": 400,
    "exam_upload_too_large": 413,
    "exam_not_finished": 400,
    "exam_attempts_exhausted": 400,
    "exam_cannot_answer": 403,
    "exam_profile_incomplete": 400,
    "exam_answers_not_found": 404,
    "exam_score_invalid": 400,
    "exam_attachment_not_found": 404,
}

# 未收录错误码时的兜底双语消息。
_DEFAULT_ERROR_MESSAGE = {"zh": "发生错误", "en": "An error occurred"}


def _error_response(code: str, status: int) -> JSONResponse:
    """构造结构化 + 双语的错误响应。"""
    return JSONResponse(
        status_code=status,
        content={
            "code": code,
            "message": ERROR_MESSAGES.get(code, _DEFAULT_ERROR_MESSAGE),
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    user_db.connect()
    user_info_db.connect()
    message_db.connect()
    exam_db.connect()
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    EXAM_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield
    user_db.close()
    user_info_db.close()
    message_db.close()
    exam_db.close()


app = FastAPI(lifespan=lifespan)


@app.exception_handler(UserDatabaseError)
async def user_database_error_handler(request: Request, exc: UserDatabaseError):
    """把数据层抛出的用户错误翻译成结构化 + 双语的响应。"""
    return JSONResponse(
        status_code=ERROR_STATUS.get(exc.code, 400),
        content={
            "code": exc.code,
            "message": ERROR_MESSAGES.get(exc.code, _DEFAULT_ERROR_MESSAGE),
        },
    )


@app.get("/")
def root():
    return {"message": "Server API", "status": "OK"}


@app.get("/api/whs")
def title():
    cfg = read_whs_config()
    return {
        "title_suffix": cfg.get("title_suffix", {}),
        "hcaptcha_site_key": cfg.get("hcaptcha", {}).get("site_key", ""),
    }


# ---------------------------------------------------------------------------
# 用户认证
# ---------------------------------------------------------------------------

@app.post("/api/user/send_code")
async def send_code(payload: dict = Body(...)):
    """向邮箱发送验证码；需先通过人机验证，防止被刷。"""
    hcaptcha_response = payload.get("hcaptcha_response") or ""
    if not await _verify_hcaptcha(hcaptcha_response):
        return _error_response("captcha_invalid", 400)
    email = (payload.get("email") or "").strip()
    if not EMAIL_RE.fullmatch(email):
        return _error_response("email_invalid", 400)

    now = time.time()
    if now - _last_send_time.get(email, 0) < SEND_COOLDOWN:
        return _error_response("send_code_too_frequent", 429)

    locale = (payload.get("locale") or "zh").strip()
    if locale not in ("zh", "en"):
        locale = "zh"

    code = f"{secrets.randbelow(10 ** 6):06d}"
    VERIFY_CODES[email] = {"code": code, "exp": now + CODE_TTL}
    _last_send_time[email] = now
    print(f"[verify-code] {email} -> {code}", flush=True)

    if locale == "zh":
        subject = "望海服务器邮箱验证码"
        body = f"您的验证码是：{code}\n\n5 分钟内有效。\n"
    else:
        subject = "WHS Verification Code"
        body = f"Your verification code is: {code}\n\nValid for 5 minutes.\n"

    if not _send_email(email, subject, body, locale):
        return _error_response("email_send_failed", 502)
    return {"success": True}


@app.get("/api/user/username_exists")
def username_exists(username: str = ""):
    """检查用户名是否已被占用。"""
    username = username.strip()
    if not USERNAME_RE.fullmatch(username):
        return _error_response("username_invalid", 400)
    return {"exists": user_db.get_user(username=username) is not None}


@app.get("/api/user/player_name_exists")
def player_name_exists(player_name: str = ""):
    """检查玩家名称（Minecraft 名称）是否已被占用。"""
    player_name = player_name.strip()
    if not USERNAME_RE.fullmatch(player_name):
        return _error_response("player_name_invalid", 400)
    return {"exists": user_info_db.player_name_exists(player_name)}


@app.post("/api/user/suggest_username")
def suggest_username(payload: dict = Body(...)):
    """基于 base 推荐一个未占用的 username；每次调用尽量返回不同结果（便于“刷新”）。"""
    base = re.sub(r"[^a-zA-Z0-9_]", "", (payload.get("base") or "").strip()) or "user"
    if user_db.get_user(username=base) is None:
        return {"username": base}
    for _ in range(100):
        candidate = f"{base}{secrets.randbelow(9999) + 1}"
        if user_db.get_user(username=candidate) is None:
            return {"username": candidate}
    i = 1
    while True:
        candidate = f"{base}{i}"
        if user_db.get_user(username=candidate) is None:
            return {"username": candidate}
        i += 1


@app.post("/api/user/register")
async def register(payload: dict = Body(...)):
    """注册：email + username + 验证码 + password + hCaptcha。"""
    email = (payload.get("email") or "").strip()
    username = (payload.get("username") or "").strip()
    code = (payload.get("code") or "").strip()
    password = payload.get("password") or ""

    if not EMAIL_RE.fullmatch(email):
        return _error_response("email_invalid", 400)
    if not USERNAME_RE.fullmatch(username):
        return _error_response("username_invalid", 400)
    if not re.fullmatch(r"[0-9a-f]{64}", password):
        return _error_response("password_invalid", 400)
    # 注册必须填写邮箱验证码（发码时已通过人机验证），提交时不再重复验证
    rec = VERIFY_CODES.get(email)
    if not rec or rec["exp"] < time.time() or rec["code"] != code:
        return _error_response("code_invalid", 400)

    # 注册时不再自动注入 fullname（留空，之后在用户设置里填）
    # 重复邮箱 / 重复用户名会抛 EmailExistsError / UsernameExistsError，由异常处理器统一翻译
    uid = user_db.create_user(username, email, "", _hash_password(password))
    user_info_db.set_user_info(uid)  # 预建一行扩展信息（性别/生日默认为空）
    VERIFY_CODES.pop(email, None)
    return {"uid": uid, "token": create_token(uid)}


@app.post("/api/user/login")
async def login(payload: dict = Body(...)):
    """登录：账密模式（identifier + password）或邮箱验证码模式（email + code）。
    仅账密模式（不填邮箱验证码）在提交时校验人机验证；验证码模式发码时已验过，不重复验证。"""
    identifier = (payload.get("identifier") or "").strip()
    password = payload.get("password")
    code = payload.get("code")

    if code is not None:
        # 邮箱验证码模式
        if not EMAIL_RE.fullmatch(identifier):
            return _error_response("email_invalid", 400)
        user = user_db.get_user(email=identifier)
        if user is None:
            return _error_response("user_not_found", 404)
        if user.get("banned"):
            return _error_response("account_banned", 403)
        if user.get("locked"):
            return _error_response("account_locked", 403)
        rec = VERIFY_CODES.get(identifier)
        if not rec or rec["exp"] < time.time() or rec["code"] != code:
            if _record_failure(user["uid"], "code"):
                return _error_response("account_locked", 403)
            return _error_response("code_invalid", 400)
        VERIFY_CODES.pop(identifier, None)
    elif password is not None:
        # 账密模式：email / UID / username（不填验证码，提交时校验人机验证）
        hcaptcha_response = payload.get("hcaptcha_response") or ""
        if not await _verify_hcaptcha(hcaptcha_response):
            return _error_response("captcha_invalid", 400)
        user = _find_by_identifier(identifier)
        if user is None:
            return _error_response("user_not_found", 404)
        if user.get("banned"):
            return _error_response("account_banned", 403)
        if user.get("locked"):
            return _error_response("account_locked", 403)
        if not _verify_password(user["password"], password):
            if _record_failure(user["uid"], "password"):
                return _error_response("account_locked", 403)
            return _error_response("invalid_credentials", 401)
    else:
        return _error_response("invalid_credentials", 401)

    _clear_failures(user["uid"])
    return {"token": create_token(user["uid"]), "user": _public_user(user)}


@app.get("/api/user/me")
def me(user: dict | None = Depends(get_current_user)):
    """返回当前登录用户（供前端刷新头像/用户态）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    return _public_user(user)


@app.post("/api/user/{uid}/unlock")
def unlock_user(uid: int, user: dict | None = Depends(get_current_user)):
    """解锁指定账号；仅 permission >= 3（admin/owner）可操作，且不能解锁权限不低于自己的用户。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    target = user_db.get_user(uid=uid)
    if target is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")
    if (user.get("permission") or 0) <= (target.get("permission") or 0):
        return _error_response("cannot_modify_higher_permission", 403)
    user_db.set_locked(uid, False)
    _clear_failures(uid)
    return {"success": True}


@app.post("/api/user/{uid}/info")
def save_user_info(uid: int, payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """保存用户完整信息（fullname + 性别 + 生日）；需本人或管理员。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if user["uid"] != uid and (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    if user_db.get_user(uid=uid) is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")

    gender = payload.get("gender")
    if gender not in (None, "male", "female"):
        return _error_response("gender_invalid", 400)

    def _parse_birth(v):
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            raise ValueError

    try:
        year = _parse_birth(payload.get("birthday_year"))
        month = _parse_birth(payload.get("birthday_month"))
        day = _parse_birth(payload.get("birthday_day"))
    except ValueError:
        return _error_response("birthday_invalid", 400)

    if year is not None and not (1900 <= year <= 2100):
        return _error_response("birthday_invalid", 400)
    if month is not None and not (1 <= month <= 12):
        return _error_response("birthday_invalid", 400)
    if day is not None and not (1 <= day <= 31):
        return _error_response("birthday_invalid", 400)
    # 级联约束：上级为空时下级必须为空
    if year is None:
        month = None
    if month is None:
        day = None

    username = payload.get("username")
    if username is not None:
        username = str(username).strip()
        if not USERNAME_RE.fullmatch(username):
            return _error_response("username_invalid", 400)
        user_db.set_username(uid, username)

    fullname = payload.get("fullname")
    if fullname is not None:
        user_db.update_user(uid, fullname=str(fullname).strip())

    player_name = payload.get("player_name")
    if player_name is not None:
        player_name = str(player_name).strip()
        if player_name:
            if not USERNAME_RE.fullmatch(player_name):
                return _error_response("player_name_invalid", 400)
            user_info_db.set_player_name(uid, player_name)

    user_info_db.set_user_info(
        uid,
        birthday_year=year,
        birthday_month=month,
        birthday_day=day,
        gender=gender,
    )
    return {"success": True}


# ---------------------------------------------------------------------------
# 用户主页 / 关注 / 简介 / 设置 / 管理员
# ---------------------------------------------------------------------------

@app.get("/api/user/{uid}")
def user_profile(uid: int, user: dict | None = Depends(get_current_user)):
    """用户主页数据：基础信息 + 扩展信息 + 关注计数 + 与当前浏览者的关系。"""
    target = user_db.get_user(uid=uid)
    if target is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")

    info = user_info_db.get_user_info(uid) or {}
    is_self = user is not None and user["uid"] == uid

    followers = user_info_db.get_followers(uid)
    followings = user_info_db.get_followings(uid)

    is_following = None
    if user is not None and not is_self:
        is_following = user_info_db.is_following(user["uid"], uid)

    data = {
        "uid": target["uid"],
        "username": target["username"],
        "fullname": target["fullname"],
        "avatar": target.get("avatar"),
        "player_name": info.get("player_name"),
        "gender": info.get("gender"),
        "birthday_year": info.get("birthday_year"),
        "birthday_month": info.get("birthday_month"),
        "birthday_day": info.get("birthday_day"),
        "profile": info.get("profile") or "",
        "followers_count": len(followers),
        "followings_count": len(followings),
        "is_self": is_self,
        "is_following": is_following,
    }
    # 仅本人可见的敏感字段（供设置页 / 管理员标签使用）
    if is_self:
        data["email"] = target["email"]
        data["permission"] = target.get("permission", 1)
        data["locked"] = bool(target.get("locked"))
        data["banned"] = bool(target.get("banned"))
    return data


@app.post("/api/user/{uid}/follow")
def follow_user(uid: int, user: dict | None = Depends(get_current_user)):
    """当前用户关注指定用户。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if user["uid"] == uid:
        return _error_response("cannot_follow_self", 400)
    if user_db.get_user(uid=uid) is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")
    user_info_db.add_follow(user["uid"], uid)
    return {
        "success": True,
        "is_following": True,
        "followers_count": len(user_info_db.get_followers(uid)),
        "followings_count": len(user_info_db.get_followings(uid)),
    }


@app.post("/api/user/{uid}/unfollow")
def unfollow_user(uid: int, user: dict | None = Depends(get_current_user)):
    """当前用户取消关注指定用户。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if user["uid"] == uid:
        return _error_response("cannot_follow_self", 400)
    if user_db.get_user(uid=uid) is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")
    user_info_db.remove_follow(user["uid"], uid)
    return {
        "success": True,
        "is_following": False,
        "followers_count": len(user_info_db.get_followers(uid)),
        "followings_count": len(user_info_db.get_followings(uid)),
    }


@app.post("/api/user/{uid}/profile")
def save_profile(uid: int, payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """保存个人简介（Markdown）；需本人或管理员。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if user["uid"] != uid and (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    if user_db.get_user(uid=uid) is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")
    profile = payload.get("profile") or ""
    if not isinstance(profile, str):
        profile = ""
    user_info_db.set_profile(uid, profile[:20000])
    return {"success": True}


@app.post("/api/user/{uid}/email")
async def change_email(uid: int, payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """修改邮箱：需向新邮箱发送验证码 + 人机验证；需本人或管理员。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if user["uid"] != uid and (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    target = user_db.get_user(uid=uid)
    if target is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")
    email = (payload.get("email") or "").strip()
    code = (payload.get("code") or "").strip()
    if not EMAIL_RE.fullmatch(email):
        return _error_response("email_invalid", 400)
    if email == target["email"]:
        return _error_response("email_same", 400)
    rec = VERIFY_CODES.get(email)
    if not rec or rec["exp"] < time.time() or rec["code"] != code:
        return _error_response("code_invalid", 400)
    other = user_db.get_user(email=email)
    if other is not None and other["uid"] != uid:
        return _error_response("email_exists", 409)
    user_db.update_user(uid, email=email)
    VERIFY_CODES.pop(email, None)
    return {"success": True}


@app.post("/api/user/password_reset_verify")
async def password_reset_verify(payload: dict = Body(...)):
    """忘记密码第一页：验证 邮箱 + 邮箱验证码 + 人机验证（不消费验证码，第二页提交时消费）。"""
    email = (payload.get("email") or "").strip()
    code = (payload.get("code") or "").strip()
    if not EMAIL_RE.fullmatch(email):
        return _error_response("email_invalid", 400)
    if user_db.get_user(email=email) is None:
        return _error_response("user_not_found", 404)
    rec = VERIFY_CODES.get(email)
    if not rec or rec["exp"] < time.time() or rec["code"] != code:
        return _error_response("code_invalid", 400)
    return {"success": True}


@app.post("/api/user/password_reset")
async def password_reset(payload: dict = Body(...)):
    """忘记密码第二页：用邮箱验证码 + 新密码重置密码；重置后解锁账号并清零失败计数。"""
    email = (payload.get("email") or "").strip()
    code = (payload.get("code") or "").strip()
    new_hash = payload.get("new_password") or ""
    if not EMAIL_RE.fullmatch(email):
        return _error_response("email_invalid", 400)
    user = user_db.get_user(email=email)
    if user is None:
        return _error_response("user_not_found", 404)
    if not re.fullmatch(r"[0-9a-f]{64}", new_hash):
        return _error_response("password_invalid", 400)
    rec = VERIFY_CODES.get(email)
    if not rec or rec["exp"] < time.time() or rec["code"] != code:
        return _error_response("code_invalid", 400)
    VERIFY_CODES.pop(email, None)
    user_db.update_user(user["uid"], password=_hash_password(new_hash))
    # 重置密码后解锁账号并清零失败计数（若之前因输错密码被锁定）
    user_db.set_locked(user["uid"], False)
    _clear_failures(user["uid"])
    return {"success": True}


@app.post("/api/user/{uid}/password_verify")
async def verify_password_change(uid: int, payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """修改密码第一页：验证 邮箱验证码(发到本人邮箱) + 旧密码 + 人机验证，全部通过才允许进入新密码页。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if user["uid"] != uid and (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    target = user_db.get_user(uid=uid)
    if target is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")
    code = (payload.get("code") or "").strip()
    old_hash = payload.get("old_password") or ""
    # 验证码发送到用户当前邮箱（前端不展示邮箱，后端取本人邮箱校验）
    email = target["email"]
    rec = VERIFY_CODES.get(email)
    if not rec or rec["exp"] < time.time() or rec["code"] != code:
        return _error_response("code_invalid", 400)
    if not _verify_password(target["password"], old_hash):
        return _error_response("old_password_invalid", 400)
    VERIFY_CODES.pop(email, None)
    return {"success": True}


@app.post("/api/user/{uid}/password")
def change_password(uid: int, payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """修改密码：需校验旧密码；需本人或管理员。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if user["uid"] != uid and (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    target = user_db.get_user(uid=uid)
    if target is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")
    old_hash = payload.get("old_password") or ""
    new_hash = payload.get("new_password") or ""
    if not re.fullmatch(r"[0-9a-f]{64}", new_hash):
        return _error_response("password_invalid", 400)
    if not _verify_password(target["password"], old_hash):
        return _error_response("old_password_invalid", 400)
    user_db.update_user(uid, password=_hash_password(new_hash))
    return {"success": True}


@app.post("/api/user/{uid}/cancel")
async def cancel_account(uid: int, payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """注销账号：验证 旧密码 + 邮箱验证码 + 人机验证 后完整删除账号与数据（仅限本人）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if user["uid"] != uid:
        return _error_response("permission_denied", 403)  # 只能注销自己
    target = user_db.get_user(uid=uid)
    if target is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")
    code = (payload.get("code") or "").strip()
    old_hash = payload.get("old_password") or ""
    email = target["email"]
    rec = VERIFY_CODES.get(email)
    if not rec or rec["exp"] < time.time() or rec["code"] != code:
        return _error_response("code_invalid", 400)
    if not _verify_password(target["password"], old_hash):
        return _error_response("old_password_invalid", 400)
    VERIFY_CODES.pop(email, None)

    # 完整清理：头像文件 + 关注列表引用 + 扩展信息 + 用户记录
    avatar = target.get("avatar")
    if avatar:
        avatar_path = AVATAR_DIR / Path(avatar).name
        if avatar_path.is_file():
            avatar_path.unlink()
    user_info_db.purge_user_refs(uid)
    user_info_db.delete_user_info(uid)
    user_db.delete_user(uid)
    return {"success": True}


@app.post("/api/user/{uid}/ban")
def set_user_banned(uid: int, payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """封禁 / 解封用户；仅管理员，且不能操作权限不低于自己的用户。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    if uid == user["uid"]:
        return _error_response("cannot_ban_self", 400)
    target = user_db.get_user(uid=uid)
    if target is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")
    if (user.get("permission") or 0) <= (target.get("permission") or 0):
        return _error_response("cannot_modify_higher_permission", 403)
    banned = bool(payload.get("banned"))
    user_db.set_banned(uid, banned)
    return {"success": True, "banned": banned}


@app.post("/api/user/{uid}/permission")
def set_user_permission(uid: int, payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """设置用户权限等级；仅管理员，不能改自己，也不能操作权限不低于自己的用户。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    if uid == user["uid"]:
        return _error_response("cannot_change_own_permission", 400)
    target = user_db.get_user(uid=uid)
    if target is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")
    if (user.get("permission") or 0) <= (target.get("permission") or 0):
        return _error_response("cannot_modify_higher_permission", 403)
    permission = payload.get("permission")
    if not isinstance(permission, int) or isinstance(permission, bool) or not (0 <= permission <= 4):
        return _error_response("invalid_permission", 400)
    user_db.set_permission(uid, permission)
    return {"success": True, "permission": permission}


@app.get("/api/admin/users")
def admin_list_users(page: int = 1, page_size: int = 10, user: dict | None = Depends(get_current_user)):
    """管理员用户列表（分页）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    all_users = user_db.list_users()
    total = len(all_users)
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    start = (page - 1) * page_size
    items = all_users[start:start + page_size]
    result = []
    for u in items:
        result.append({
            "uid": u["uid"],
            "username": u["username"],
            "fullname": u["fullname"],
            "avatar": u.get("avatar"),
            "email": u["email"],
            "permission": u.get("permission", 1),
            "locked": bool(u.get("locked")),
            "banned": bool(u.get("banned")),
        })
    return {"total": total, "page": page, "page_size": page_size, "users": result}


# ---------------------------------------------------------------------------
# 头像
# ---------------------------------------------------------------------------

@app.post("/api/user/{uid}/avatar")
async def upload_avatar(uid: int, file: UploadFile = File(...), user: dict | None = Depends(get_current_user)):
    """上传头像：校验类型/大小，落盘并更新 users.avatar（需本人或管理员）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if user["uid"] != uid and (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    ext = AVATAR_CONTENT_TYPES.get(file.content_type)
    if ext is None:
        return _error_response("avatar_unsupported_type", 400)
    data = await file.read(MAX_AVATAR_SIZE + 1)
    if len(data) > MAX_AVATAR_SIZE:
        return _error_response("avatar_too_large", 413)
    existing = user_db.get_user(uid=uid)
    if existing is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")
    filename = f"{uuid.uuid4().hex}{ext}"
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    (AVATAR_DIR / filename).write_bytes(data)
    old = existing.get("avatar")
    if old:
        old_path = AVATAR_DIR / Path(old).name
        if old_path.is_file():
            old_path.unlink()
    user_db.update_user(uid, avatar=filename)
    return {"avatar": filename}


@app.get("/api/user/{uid}/avatar")
def get_avatar(uid: int):
    """读取头像；无头像时前端使用默认头像。"""
    user = user_db.get_user(uid=uid)
    if user is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")
    avatar = user.get("avatar")
    if not avatar:
        return _error_response("avatar_not_found", 404)
    avatar_path = AVATAR_DIR / Path(avatar).name
    if not avatar_path.is_file():
        return _error_response("avatar_not_found", 404)
    return FileResponse(avatar_path)


# ---------------------------------------------------------------------------
# 其它
# ---------------------------------------------------------------------------

@app.get("/api/message/system")
def system_messages(user: dict | None = Depends(get_current_user)):
    """系统消息列表（所有人可见）；登录时附带每条消息当前用户是否已读。"""
    messages = message_db.list_system_messages()
    for m in messages:
        # 不向客户端暴露其他用户的已读 uid 列表
        m.pop("read_uids", None)
        if user is None:
            m["is_read"] = None
        else:
            m["is_read"] = message_db.is_read_by(m["id"], user["uid"])
    return {"messages": messages}


@app.get("/api/message/unread_count")
def message_unread_count(user: dict | None = Depends(get_current_user)):
    """当前用户的未读消息数（系统 + 定向；未登录不允许）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    count = 0
    for m in message_db.list_system_messages():
        if not message_db.is_read_by(m["id"], user["uid"]):
            count += 1
    for m in message_db.list_user_messages(user["uid"]):
        if not message_db.is_read_by(m["id"], user["uid"]):
            count += 1
    return {"count": count}


@app.post("/api/message/{message_id}/read")
def mark_message_read(message_id: int, user: dict | None = Depends(get_current_user)):
    """把当前用户标记为该消息已读（幂等）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if message_db.get_message(message_id) is None:
        return _error_response("message_not_found", 404)
    message_db.add_read_user(message_id, user["uid"])
    return {"success": True, "is_read": True}


# ---------------------------------------------------------------------------
# 入服考试
# ---------------------------------------------------------------------------

def _load_exam() -> dict | None:
    """加载并校验考试配置；失败返回 None（错误码由调用方统一处理）。"""
    try:
        return load_exam_config()
    except ExamConfigError:
        return None


def _grade_exam_question(q: dict, answer) -> tuple[int, bool | None]:
    """自动判分：返回 (得分, 是否正确)。主观题（题型或标记）/ 无标准答案恒 0 分且 correct=None。"""
    if q.get("subjective") or q["type"] == "subjective":
        return 0, None
    ans = q.get("answer")
    if ans is None:
        return 0, None
    score = int(q.get("score", 0))
    qtype = q["type"]
    if qtype == "single_choice":
        correct = answer == ans
        return (score if correct else 0), correct
    if qtype == "multiple_choice":
        correct = isinstance(answer, list) and sorted(answer) == sorted(ans)
        return (score if correct else 0), correct
    if qtype == "fill_blank":
        text = str(answer).strip()
        correct = any(text == str(a).strip() for a in ans)
        return (score if correct else 0), correct
    return 0, None


def _exam_question_public(qid: int, q: dict) -> dict:
    """题目对外结构（不含标准答案，防止作弊）。"""
    item = {
        "id": qid,
        "type": q["type"],
        "subject": q["subject"],
        "score": int(q.get("score", 0)),
        "subjective": bool(q.get("subjective", False)),
        "image": q.get("image") or "",
        "allow_upload": bool(q.get("allow_upload", False)),
    }
    if q.get("options"):
        item["options"] = [
            {"key": k, "text": opt.get("text", ""), "image": opt.get("image", "")}
            for k, opt in q["options"].items()
        ]
    return item


@app.get("/api/exam")
def exam_config(user: dict | None = Depends(get_current_user)):
    """考试配置（不含标准答案，防止作弊）；需登录。"""
    if user is None:
        return _error_response("unauthorized", 401)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    questions = [_exam_question_public(qid, q) for qid, q in cfg["questions"].items()]
    questions.sort(key=lambda x: x["id"])
    return {"total_score": cfg["total_score"], "questions": questions}


@app.get("/api/exam/progress")
def exam_progress(user: dict | None = Depends(get_current_user)):
    """当前用户答题进度（每题的已答内容 / 附件 / 得分）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    records = exam_db.get_answers(user["uid"])
    answered = {
        qid: {
            "answer": rec.get("answer"),
            "attachment": rec.get("attachment"),
            "obtained_score": rec.get("obtained_score", 0),
            "answered_at": rec.get("answered_at"),
        }
        for qid, rec in records.items()
    }
    all_ids = set(cfg["questions"].keys())
    return {
        "answered": answered,
        "answered_count": len(answered),
        "total_questions": len(all_ids),
        "all_answered": all_ids.issubset(answered.keys()),
    }


@app.post("/api/exam/answer")
def exam_answer(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """提交某题答案（每答一题、锁存一题）；自动判分并返回该题得分。"""
    if user is None:
        return _error_response("unauthorized", 401)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    try:
        qid = int(payload.get("question_id"))
    except (TypeError, ValueError):
        return _error_response("exam_question_not_found", 404)
    q = cfg["questions"].get(qid)
    if q is None:
        return _error_response("exam_question_not_found", 404)

    answer = payload.get("answer")
    attachment = payload.get("attachment") or None
    options = q.get("options") or {}

    # 按题型校验答案格式
    if q["type"] == "single_choice":
        if not isinstance(answer, str) or answer not in options:
            return _error_response("exam_answer_invalid", 400)
    elif q["type"] == "multiple_choice":
        if not isinstance(answer, list) or not all(
            isinstance(x, str) and x in options for x in answer
        ):
            return _error_response("exam_answer_invalid", 400)
    elif q["type"] == "fill_blank":
        if not isinstance(answer, str):
            return _error_response("exam_answer_invalid", 400)
    else:  # subjective 主观题：文本作答，不计分
        if not isinstance(answer, str):
            return _error_response("exam_answer_invalid", 400)
    # 附件仅填空题且 allow_upload 时允许
    if attachment:
        if q["type"] != "fill_blank" or not q.get("allow_upload"):
            return _error_response("exam_upload_not_allowed", 400)

    score, correct = _grade_exam_question(q, answer)
    exam_db.save_answer(user["uid"], qid, answer, score, attachment)
    return {
        "success": True,
        "question_id": qid,
        "obtained_score": score,
        "correct": correct,
    }


@app.post("/api/exam/upload")
async def exam_upload(
    question_id: int = Form(...),
    file: UploadFile = File(...),
    user: dict | None = Depends(get_current_user),
):
    """上传答题附件（图片）；仅填空题且 allow_upload 的题目允许。"""
    if user is None:
        return _error_response("unauthorized", 401)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    q = cfg["questions"].get(question_id)
    if q is None:
        return _error_response("exam_question_not_found", 404)
    if q["type"] != "fill_blank" or not q.get("allow_upload"):
        return _error_response("exam_upload_not_allowed", 400)
    ext = EXAM_UPLOAD_CONTENT_TYPES.get(file.content_type)
    if ext is None:
        return _error_response("exam_upload_unsupported", 400)
    data = await file.read(MAX_EXAM_UPLOAD_SIZE + 1)
    if len(data) > MAX_EXAM_UPLOAD_SIZE:
        return _error_response("exam_upload_too_large", 413)
    filename = f"u{user['uid']}_q{question_id}_{uuid.uuid4().hex}{ext}"
    EXAM_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (EXAM_UPLOAD_DIR / filename).write_bytes(data)
    return {"success": True, "attachment": filename}


@app.get("/api/exam/attachment/{filename}")
def exam_attachment(filename: str, user: dict | None = Depends(get_current_user)):
    """读取答题附件（图片）；仅本人或管理员。"""
    if user is None:
        return _error_response("unauthorized", 401)
    name = Path(filename).name
    match = re.match(r"^u(\d+)_q\d+_[0-9a-f]+\.(jpg|png|webp|gif)$", name)
    if not match:
        return _error_response("exam_attachment_not_found", 404)
    owner = int(match.group(1))
    if owner != user["uid"] and (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    path = EXAM_UPLOAD_DIR / name
    if not path.is_file():
        return _error_response("exam_attachment_not_found", 404)
    return FileResponse(path)


@app.post("/api/exam/submit")
def exam_submit(user: dict | None = Depends(get_current_user)):
    """交卷汇总：返回总分 / 已得分数 / 完成情况。"""
    if user is None:
        return _error_response("unauthorized", 401)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    records = exam_db.get_answers(user["uid"])
    obtained = sum(rec.get("obtained_score", 0) for rec in records.values())
    all_ids = set(cfg["questions"].keys())
    answered_ids = set(records.keys())
    return {
        "success": True,
        "total_score": cfg["total_score"],
        "obtained_score": obtained,
        "answered_count": len(records),
        "total_questions": len(all_ids),
        "all_answered": answered_ids.issubset(all_ids),
    }


# ---------------------------------------------------------------------------
# 入服考试：个人信息 / 完成判分 / 申请重审 / 管理端
# ---------------------------------------------------------------------------

@app.get("/api/exam/profile")
def exam_profile(user: dict | None = Depends(get_current_user)):
    """当前考生信息（游戏名 / QQ / 次数 / 是否及格）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    profile = exam_db.get_profile(user["uid"]) or {}
    return {
        "player_name": profile.get("player_name", ""),
        "qq_name": profile.get("qq_name", ""),
        "qq_number": profile.get("qq_number", ""),
        "attempts": int(profile.get("attempts", 0)),
        "passed": bool(profile.get("passed")),
        "can_answer": exam_db.can_answer(user["uid"]),
    }


@app.post("/api/exam/profile")
def exam_save_profile(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """实时保存个人信息（游戏名 / QQ 名称 / QQ 号）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    player_name = str(payload.get("player_name") or "").strip()[:64]
    qq_name = str(payload.get("qq_name") or "").strip()[:64]
    qq_number = str(payload.get("qq_number") or "").strip()[:32]
    if not USERNAME_RE.fullmatch(player_name):
        return _error_response("player_name_invalid", 400)
    exam_db.save_profile(user["uid"], player_name, qq_name, qq_number)
    return {"success": True}


@app.post("/api/exam/reset")
def exam_reset(user: dict | None = Depends(get_current_user)):
    """重新作答：清空本人的答题记录（次数限制内允许）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if not exam_db.can_answer(user["uid"]):
        return _error_response("exam_cannot_answer", 403)
    exam_db.delete_answers(user["uid"])
    return {"success": True}


def _apply_exam_pass(uid: int) -> str | None:
    """及格处理：注入 player_name + 权限升级（仅 <2 时）+ 标记 passed。
    成功返回 None；失败返回错误码（exam_profile_incomplete / player_name_exists）。"""
    profile = exam_db.get_profile(uid) or {}
    pname = (profile.get("player_name") or "").strip()
    if not pname:
        return "exam_profile_incomplete"
    own = (user_info_db.get_user_info(uid) or {}).get("player_name")
    if pname != own and user_info_db.player_name_exists(pname):
        return "player_name_exists"
    user_info_db.set_player_name(uid, pname)
    current_permission = user_db.get_user(uid=uid).get("permission") or 0
    if current_permission < 2:
        user_db.set_permission(uid, 2)
    exam_db.mark_passed(uid)
    return None


@app.post("/api/exam/finish")
def exam_finish(user: dict | None = Depends(get_current_user)):
    """完成答卷：判分汇总、次数 +1；及格则注入 player_name 并升级为 player(2)。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if not exam_db.can_answer(user["uid"]):
        return _error_response("exam_cannot_answer", 403)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    answers = exam_db.get_answers(user["uid"])
    all_ids = set(cfg["questions"].keys())
    if not all_ids.issubset(answers.keys()):
        return _error_response("exam_not_finished", 400)

    total = cfg["total_score"]
    obtained = sum(rec.get("obtained_score", 0) for rec in answers.values())
    passed = obtained >= total * 0.6
    if passed:
        err = _apply_exam_pass(user["uid"])
        if err:
            return _error_response(err, ERROR_STATUS.get(err, 400))

    attempts = exam_db.increment_attempts(user["uid"])
    return {
        "success": True,
        "total_score": total,
        "obtained_score": obtained,
        "passed": passed,
        "attempts": attempts,
        "can_answer": exam_db.can_answer(user["uid"]),
    }


@app.post("/api/exam/review")
def exam_review(user: dict | None = Depends(get_current_user)):
    """申请重审答题卡：向所有管理员推送定向消息并发送邮件。"""
    if user is None:
        return _error_response("unauthorized", 401)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    answers = exam_db.get_answers(user["uid"])
    if not answers:
        return _error_response("exam_answers_not_found", 404)
    obtained = sum(rec.get("obtained_score", 0) for rec in answers.values())
    profile = exam_db.get_profile(user["uid"]) or {}
    target = user_db.get_user(uid=user["uid"])
    admins = [u for u in user_db.list_users() if (u.get("permission") or 0) >= 3]

    title = "答题卡重审申请"
    content = (
        f"用户 {target['username']}（UID {user['uid']}）申请重审答题卡。\n"
        f"游戏名称：{profile.get('player_name', '')}\n"
        f"QQ 名称：{profile.get('qq_name', '')}\n"
        f"QQ 号：{profile.get('qq_number', '')}\n"
        f"当前得分：{obtained} / {cfg['total_score']}\n"
        f"请管理员前往「考试管理」查看该用户的答题卡。"
    )
    sent = 0
    for admin in admins:
        message_db.create_message(
            title, content, user["uid"], scope="user", target_uid=admin["uid"]
        )
        _send_email(
            admin["email"],
            f"[望海服务器] 答题卡重审申请 - {target['username']}",
            content,
            "zh",
        )
        sent += 1
    return {"success": True, "notified": sent}


@app.get("/api/admin/exam/candidates")
def admin_exam_candidates(
    page: int = 1,
    page_size: int = 10,
    user: dict | None = Depends(get_current_user),
):
    """考试管理：有答卷的考生列表（分页）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    uids = exam_db.list_answered_uids()
    total = len(uids)
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    items = uids[(page - 1) * page_size : page * page_size]
    result = []
    for uid in items:
        u = user_db.get_user(uid=uid)
        if u is None:
            continue
        prof = exam_db.get_profile(uid) or {}
        result.append({
            "uid": uid,
            "username": u["username"],
            "avatar": u.get("avatar"),
            "player_name": prof.get("player_name") or "",
            "attempts": int(prof.get("attempts", 0)),
            "passed": bool(prof.get("passed")),
            "answered_count": len(exam_db.get_answers(uid)),
        })
    return {"total": total, "page": page, "page_size": page_size, "candidates": result}


@app.get("/api/admin/exam/answers/{uid}")
def admin_exam_answers(uid: int, user: dict | None = Depends(get_current_user)):
    """查看某考生答题卡（题目 + 答案 + 得分）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    answers = exam_db.get_answers(uid)
    if not answers:
        return _error_response("exam_answers_not_found", 404)
    profile = exam_db.get_profile(uid) or {}
    per = {}
    for qid, q in cfg["questions"].items():
        rec = answers.get(qid)
        per[qid] = {
            "question": _exam_question_public(qid, q),
            "answer": rec.get("answer") if rec else None,
            "attachment": rec.get("attachment") if rec else None,
            "obtained_score": rec.get("obtained_score", 0) if rec else 0,
            "answered": rec is not None,
        }
    total = cfg["total_score"]
    obtained = sum(rec.get("obtained_score", 0) for rec in answers.values())
    return {
        "uid": uid,
        "profile": profile,
        "answers": per,
        "total_score": total,
        "obtained_score": obtained,
    }


@app.post("/api/admin/exam/score")
def admin_exam_score(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """管理员修改某考生某题的实际得分（0 ~ 该题满分）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    try:
        uid = int(payload.get("uid"))
        question_id = int(payload.get("question_id"))
    except (TypeError, ValueError):
        return _error_response("exam_score_invalid", 400)
    score = payload.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool) or score < 0:
        return _error_response("exam_score_invalid", 400)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    q = cfg["questions"].get(question_id)
    if q is None:
        return _error_response("exam_question_not_found", 404)
    if int(score) > int(q.get("score", 0)):
        return _error_response("exam_score_invalid", 400)
    if exam_db.get_answer(uid, question_id) is None:
        return _error_response("exam_answers_not_found", 404)
    exam_db.set_score(uid, question_id, int(score))
    # 改分后重新汇总总分并判定及格状态（达标且未通过则应用及格处理）
    records = exam_db.get_answers(uid)
    obtained_total = sum(r.get("obtained_score", 0) for r in records.values())
    passed_now = obtained_total >= cfg["total_score"] * 0.6
    passed_flag = bool((exam_db.get_profile(uid) or {}).get("passed"))
    if passed_now and not passed_flag:
        err = _apply_exam_pass(uid)
        if err:
            return _error_response(err, ERROR_STATUS.get(err, 400))
    return {"success": True, "obtained_score": int(score), "passed": passed_now}


@app.delete("/api/admin/exam/answers/{uid}")
def admin_exam_delete_answers(uid: int, user: dict | None = Depends(get_current_user)):
    """删除某考生答卷（重置：清空答题记录、次数与及格标记，允许重新作答）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    exam_db.reset_candidate(uid)
    return {"success": True}


@app.get("/api/message/{user_id}")
def user_message(user_id: str, user: dict | None = Depends(get_current_user)):
    """定向消息（仅本人或管理员可看）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return _error_response("message_not_found", 404)
    if uid != user["uid"] and (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    messages = message_db.list_user_messages(uid)
    for m in messages:
        m.pop("read_uids", None)
        m["is_read"] = message_db.is_read_by(m["id"], user["uid"])
    return {"messages": messages}


@app.post("/api/admin/messages")
def publish_message(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """管理员发布系统消息（标题 + Markdown 内容）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    title = payload.get("title") or ""
    content = payload.get("content") or ""
    if not isinstance(title, str) or not title.strip():
        return _error_response("message_title_empty", 400)
    if not isinstance(content, str) or not content.strip():
        return _error_response("message_content_empty", 400)
    title = title.strip()[:100]
    content = content.strip()[:20000]
    message_id = message_db.create_message(title, content, user["uid"], scope="system")
    return {"success": True, "message": message_db.get_message(message_id)}


@app.delete("/api/admin/messages/{message_id}")
def delete_message(message_id: int, user: dict | None = Depends(get_current_user)):
    """管理员删除自己发布的消息。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    msg = message_db.get_message(message_id)
    if msg is None:
        return _error_response("message_not_found", 404)
    if msg["author_uid"] != user["uid"]:
        return _error_response("permission_denied", 403)
    message_db.delete_message(message_id)
    return {"success": True}
