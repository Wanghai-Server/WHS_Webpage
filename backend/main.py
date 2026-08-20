import asyncio
import base64
import datetime
import hashlib
import hmac
import json
import re
import secrets
import smtplib
import sys
import threading
import time
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from email.message import EmailMessage
from pathlib import Path

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

# 将项目根目录加入 sys.path，以便导入与 backend/ 同级的 data 包。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data import read_config, read_whs_config
from data.exam import (
    ExamConfigError,
    fill_blank_blanks,
    load_exam_config,
)
from data.main.database.exam_database import ExamDatabase
from data.main.database.message_database import MessageDatabase
from data.main.database.user_database import (
    ERROR_MESSAGES as USER_DB_ERROR_MESSAGES,
    UserDatabase,
    UserDatabaseError,
    UserInfoDatabase,
)

# 用户数据库实例：随服务启动连接、随服务关闭释放。
user_db = UserDatabase()
user_info_db = UserInfoDatabase()
message_db = MessageDatabase()
exam_db = ExamDatabase()

# MCDR 插件通信的 WS 命令服务：仅监听环回地址，端口来自 config.json 的 ws_port。
from ws_server import WsCommandServer  # noqa: E402

ws_server = WsCommandServer("127.0.0.1", int(read_config().get("ws_port") or 8765))

# MCDR 每 5 分钟主动上报的服务器运行数据（数据来源：RCON `tick query` + `list`，见 mcdr2web 插件）。
# 由 ws_server 的 report_tps 指令处理器更新，/api/server/status 读取。
_SERVER_TPS_CACHE: dict = {
    "tps": None,
    "mspt": None,
    "healthy": None,
    "max": None,
    "updated_at": None,
}


async def _handle_report_tps(data) -> dict:
    """处理 MCDR 主动上报的 TPS/MSPT/玩家上限（每 tps_report_interval 秒一次，默认 5 分钟）。"""
    if isinstance(data, dict):
        _SERVER_TPS_CACHE["tps"] = data.get("tps")
        _SERVER_TPS_CACHE["mspt"] = data.get("mspt")
        _SERVER_TPS_CACHE["healthy"] = data.get("healthy")
        _SERVER_TPS_CACHE["max"] = data.get("max")
        _SERVER_TPS_CACHE["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        print(
            f"[server-status] MCDR 上报 TPS={data.get('tps')} MSPT={data.get('mspt')} "
            f"max={data.get('max')}",
            flush=True,
        )
    return {"success": True}


ws_server.register("report_tps")(_handle_report_tps)

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
MAX_EXAM_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB
EXAM_UPLOAD_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

# 试卷附图（题目/选项图片，管理员上传）存储目录、大小上限、允许的 MIME 类型。
EXAM_IMAGE_DIR = PROJECT_ROOT / "data" / "exam_image"
MAX_EXAM_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
EXAM_IMAGE_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

# 试卷说明文档（仅 .docx，管理员上传），与附图共用 exam_image 目录。
MAX_EXAM_DOC_SIZE = 10 * 1024 * 1024  # 10MB

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


class UserNotActiveError(Exception):
    """账号被封禁或锁定时抛出，携带错误码（account_banned / account_locked）。

    由全局异常处理器统一翻译成 403 + 双语错误体。
    """

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def check_user_active(user: dict | None) -> str | None:
    """复用函数：判断用户是否被封禁 / 锁定。

    :param user: 用户记录（可为 None）。
    :return: 正常返回 None；被封禁返回 ``"account_banned"``，
             被锁定返回 ``"account_locked"``。
    """
    if user is None:
        return None
    if user.get("banned"):
        return "account_banned"
    if user.get("locked"):
        return "account_locked"
    return None


def get_current_user(authorization: str = Header(None)):
    """FastAPI 依赖：从 Authorization: Bearer <token> 解析当前登录用户；未登录返回 None。

    被封禁 / 锁定的账号在此统一拒绝（抛 UserNotActiveError -> 403 错误码），
    因此所有 ``Depends(get_current_user)`` 的受保护接口都会拦截。
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    payload = verify_token(authorization[7:])
    if payload is None:
        return None
    user = user_db.get_user(uid=payload.get("uid"))
    if user is None:
        return None
    err = check_user_active(user)
    if err:
        raise UserNotActiveError(err)
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
    "new_permission_higher": {
        "zh": "不能把用户权限设置得高于自己的权限",
        "en": "Cannot set a permission higher than your own",
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
    "exam_config_invalid": {
        "zh": "试卷配置不合法，请检查后重试",
        "en": "Invalid exam configuration, please check and retry",
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
        "zh": "附件大小不能超过 20MB",
        "en": "Attachment must not exceed 20MB",
    },
    "exam_image_unsupported": {
        "zh": "仅支持上传图片（jpg/png/webp/gif）",
        "en": "Only jpg/png/webp/gif images are supported",
    },
    "exam_image_too_large": {
        "zh": "图片大小不能超过 5MB",
        "en": "Image must not exceed 5MB",
    },
    "exam_image_not_found": {
        "zh": "图片不存在",
        "en": "Image not found",
    },
    "exam_doc_unsupported": {
        "zh": "仅支持上传 .docx 文档",
        "en": "Only .docx documents are supported",
    },
    "exam_doc_too_large": {
        "zh": "文档大小不能超过 10MB",
        "en": "Document must not exceed 10MB",
    },
    "exam_doc_not_found": {
        "zh": "文档不存在",
        "en": "Document not found",
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
    "exam_review_already_requested": {
        "zh": "本次答卷已提交过重审申请，请勿重复提交",
        "en": "A review request has already been submitted for this attempt",
    },
    "message_not_found": {
        "zh": "消息不存在",
        "en": "Message not found",
    },
    "alt_accounts_full": {
        "zh": "小号数量已达上限（最多两个）",
        "en": "Alt account limit reached (max 2)",
    },
    "premium_invalid": {
        "zh": "正版状态取值不合法",
        "en": "Invalid premium status",
    },
    "no_main_account": {
        "zh": "请先绑定主账号（游戏名称）",
        "en": "Please bind a main account first",
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
    "new_permission_higher": 400,
    "email_same": 400,
    "message_content_empty": 400,
    "message_title_empty": 400,
    "message_not_found": 404,
    "exam_config_error": 500,
    "exam_config_invalid": 400,
    "exam_question_not_found": 404,
    "exam_answer_invalid": 400,
    "exam_upload_not_allowed": 400,
    "exam_upload_unsupported": 400,
    "exam_upload_too_large": 413,
    "exam_image_unsupported": 400,
    "exam_image_too_large": 413,
    "exam_image_not_found": 404,
    "exam_doc_unsupported": 400,
    "exam_doc_too_large": 413,
    "exam_doc_not_found": 404,
    "exam_not_finished": 400,
    "exam_attempts_exhausted": 400,
    "exam_cannot_answer": 403,
    "exam_profile_incomplete": 400,
    "exam_answers_not_found": 404,
    "exam_score_invalid": 400,
    "exam_attachment_not_found": 404,
    "exam_review_already_requested": 400,
    "alt_accounts_full": 400,
    "premium_invalid": 400,
    "no_main_account": 400,
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
    # 记录主事件循环引用：供线程池中的同步端点经 run_coroutine_threadsafe 调用 WS 命令服务
    global MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()
    user_db.connect()
    user_info_db.connect()
    message_db.connect()
    exam_db.connect()
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    EXAM_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    EXAM_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    # 启动 MCDR 插件通信的 WS 命令服务（仅监听环回地址，端口来自 config.json 的 ws_port）
    await ws_server.start()
    ws_serve_task = asyncio.create_task(ws_server.wait_until_closed())

    yield

    await ws_server.stop()
    if ws_serve_task:
        await ws_serve_task
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


@app.exception_handler(UserNotActiveError)
async def user_not_active_error_handler(request: Request, exc: UserNotActiveError):
    """封禁 / 锁定账号的统一拒绝：403 + 结构化双语错误码（前端用 tips 提示）。"""
    return JSONResponse(
        status_code=ERROR_STATUS.get(exc.code, 403),
        content={
            "code": exc.code,
            "message": ERROR_MESSAGES.get(exc.code, _DEFAULT_ERROR_MESSAGE),
        },
    )

def _attach_message_author(msg: dict) -> None:
    """把消息的 author_uid 解析为发布者名称（author_name），写入消息字典。"""
    author = user_db.get_user(uid=msg.get("author_uid"))
    if author:
        msg["author_name"] = author.get("fullname") or author.get("username") or ""
    else:
        msg["author_name"] = ""


# ---------------------------------------------------------------------------
# 服务器实时状态：全部数据来自 MCDR 插件（WS 通路），后端每 5 分钟刷新缓存。
# 路由在 api/server.py（/api/server/status）。
# ---------------------------------------------------------------------------

# 状态缓存：{data, fetched_at}。首次请求时触发拉取，之后每 SERVER_STATUS_TTL 秒刷新。
_SERVER_STATUS_LOCK = threading.Lock()
_SERVER_STATUS_CACHE: dict = {"data": None, "fetched_at": 0.0}
SERVER_STATUS_TTL = 300  # 5 分钟


# ---------------------------------------------------------------------------
# MCDR 插件通信：WS 请求封装 + 在线名单 / 白名单业务
# （ws_server 为 asyncio 服务、运行在主事件循环；线程池中的同步端点
#   须经 run_coroutine_threadsafe 提交请求，见下方 ws_request_sync）
# ---------------------------------------------------------------------------

# 主事件循环引用：由 lifespan 启动时记录（模块导入阶段为 None）。
MAIN_LOOP: asyncio.AbstractEventLoop | None = None


def ws_request_sync(command: str, data=None, timeout: float = 10.0) -> dict:
    """同步调用 WS 命令服务（供线程池中的同步端点使用）。

    返回完整响应 dict（{"request_id", "success", "data"}）；
    WS 未启动 / 未连接 / 超时等异常时返回 {"success": False, "data": 原因}，
    绝不向调用方抛异常。
    """
    if MAIN_LOOP is None:
        return {"success": False, "data": "WS 服务未启动"}
    try:
        future = asyncio.run_coroutine_threadsafe(
            ws_server.request(command, data, timeout), MAIN_LOOP
        )
        return future.result(timeout + 1)
    except Exception as exc:
        return {"success": False, "data": f"{type(exc).__name__}: {exc}"}


# 假人前缀：以 bot_ 开头的在线玩家视为假人，不计入官网在线人数。
BOT_PREFIX = "bot_"


def fetch_online_players() -> dict | None:
    """向 MCDR 获取当前在线名单，并按 bot_ 前缀区分假人 / 真人。

    :return: {"players": 全部名单, "real": 真人列表, "bots": 假人列表}；
             WS 不可用（未启动 / 未连接 / 失败）时返回 None（由调用方回退）。
    """
    resp = ws_request_sync("get_player_list", timeout=3.0)
    if not resp.get("success"):
        return None
    data = resp.get("data")
    if isinstance(data, str):
        data = [data]
    if not isinstance(data, list):
        return None
    players = [str(p) for p in data if str(p).strip()]
    bots = [n for n in players if n.lower().startswith(BOT_PREFIX)]
    real = [n for n in players if not n.lower().startswith(BOT_PREFIX)]
    return {"players": players, "real": real, "bots": bots}


def is_player_online(player: str) -> bool:
    """判断某个玩家是否在线（预留，前端暂未使用）。"""
    resp = ws_request_sync("is_online", {"player": player}, timeout=3.0)
    return bool(resp.get("success") and resp.get("data"))


def get_whitelist() -> list[str]:
    """获取白名单列表（预留，前端暂未使用；之后作为关于页成员墙）。"""
    resp = ws_request_sync("get_whitelist", timeout=3.0)
    data = resp.get("data") if resp.get("success") else []
    if isinstance(data, str):
        data = [data]
    if not isinstance(data, list):
        return []
    return [str(p) for p in data if str(p).strip()]


def _whitelist_op_ok(resp: dict) -> bool:
    """白名单增删操作的幂等判定：success 为 True 即成功；
    或 MCDR 端报"已存在 / 不存在"（already exist / is not exist 等）时，
    同样视为已达到目标状态（不在调用方制造错误）。"""
    if resp.get("success"):
        return True
    msg = str(resp.get("data") or "").lower()
    return "already" in msg or "not exist" in msg or "不存在" in msg or "已存在" in msg


def add_player_whitelist(player: str) -> dict:
    """把玩家加入白名单（幂等：已在白名单视为成功）。"""
    resp = ws_request_sync("add_player", {"player": player}, timeout=10.0)
    ok = _whitelist_op_ok(resp)
    if not ok:
        print(f"[ws-whitelist] 添加白名单失败 {player}: {resp}", flush=True)
    return {
        "success": ok,
        "player": player,
        "note": "added" if resp.get("success") else str(resp.get("data") or ""),
    }


def remove_player_whitelist(player: str) -> dict:
    """把玩家移出白名单（幂等：不在白名单视为成功）。"""
    resp = ws_request_sync("remove_player", {"player": player}, timeout=10.0)
    ok = _whitelist_op_ok(resp)
    if not ok:
        print(f"[ws-whitelist] 移除白名单失败 {player}: {resp}", flush=True)
    return {
        "success": ok,
        "player": player,
        "note": "removed" if resp.get("success") else str(resp.get("data") or ""),
    }


def remove_user_whitelist(uid: int) -> dict:
    """移除某用户的全部白名单关联：主账号（player_name）+ 所有小号。

    供管理员封禁时调用：把该用户在游戏服务器中的入口全部收回。
    """
    info = user_info_db.get_user_info(uid) or {}
    names = []
    pname = (info.get("player_name") or "").strip()
    if pname:
        names.append(pname)
    names.extend(user_info_db.get_alt_accounts(uid))
    results = [remove_player_whitelist(name) for name in names]
    return {"success": all(r["success"] for r in results), "results": results}


# ---------------------------------------------------------------------------
# 入服考试：辅助逻辑（路由在 api/exam.py）
# ---------------------------------------------------------------------------

def _load_exam() -> dict | None:
    """加载并校验考试配置；失败返回 None（错误码由调用方统一处理）。"""
    try:
        return load_exam_config()
    except ExamConfigError:
        return None


def _grade_exam_question(q: dict, answer) -> tuple[int, bool | None]:
    """自动判分：返回 (得分, 是否正确)。

    - 单选题：正确给全分，错误 0；
    - 多选题：部分对得部分分 —— 分数 = 总分 × (选中的正确选项数 ÷ 标准答案正确选项数)，
      全对满分，选到任一错误选项得 0；
    - 填空题：按空给分，每空均分本题总分，答对几空得几空分；
    - 主观题（题型或标记）/ 无标准答案恒 0 分且 correct=None。
    部分分一律向下取整（不出现小数）。
    """
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
        if not isinstance(answer, list) or not answer:
            return 0, False
        # 选到任一错误选项 -> 0 分
        if any(a not in ans for a in answer):
            return 0, False
        # 全对 -> 满分
        if sorted(answer) == sorted(ans):
            return score, True
        # 部分对：按 选中的正确选项数 / 标准答案正确选项数 计分，向下取整
        correct_count = sum(1 for a in answer if a in ans)
        return (score * correct_count) // len(ans), False
    if qtype == "fill_blank":
        blanks = fill_blank_blanks(ans)  # 每空的可接受答案
        if len(blanks) == 1:
            # 单项填空：考生答案为一个字符串
            text = str(answer).strip()
            correct = any(text == str(a).strip() for a in blanks[0])
            return (score if correct else 0), correct
        # 多项填空：每空均分本题总分；答对几空得几空分（向下取整）
        if not isinstance(answer, list) or len(answer) != len(blanks):
            return 0, False
        correct_count = 0
        for i, acceptable in enumerate(blanks):
            if any(str(answer[i]).strip() == str(a).strip() for a in acceptable):
                correct_count += 1
        correct = correct_count == len(blanks)
        return (score * correct_count) // len(blanks), correct
    return 0, None


def _exam_question_public(qid: int, q: dict) -> dict:
    """题目对外结构（不含标准答案，防止作弊）。"""
    item = {
        "id": qid,
        "type": q["type"],
        "subject": q["subject"],
        "score": int(q.get("score", 0)),
        "subjective": bool(q.get("subjective", False)),
        # 附图（多张；兼容旧单个 image 字段）
        "images": [i for i in (q.get("images") or []) if isinstance(i, str)]
        or ([q["image"]] if q.get("image") else []),
        "allow_upload": bool(q.get("allow_upload", False)),
    }
    if q["type"] == "fill_blank":
        # 填空数（多项填空 > 1；单项填空恒为 1），供前端渲染对应数量的输入框
        item["blank_count"] = len(fill_blank_blanks(q.get("answer")))
    if q.get("options"):
        item["options"] = [
            {"key": k, "text": opt.get("text", ""), "image": opt.get("image", "")}
            for k, opt in q["options"].items()
        ]
    return item


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
    # 出成绩（及格）即自动加入游戏服务器白名单（幂等；WS 不可用时仅记日志，不影响出成绩）
    add_player_whitelist(pname)
    return None


def _notify_exam_passed(uid: int, admin_uid: int) -> None:
    """复审通过后通知考生：定向消息（消息盒子可见）+ 邮件。

    :param uid: 考生 uid。
    :param admin_uid: 执行复审并通过的管理员 uid（作为消息作者）。
    """
    target = user_db.get_user(uid=uid)
    if target is None:
        return
    title = "入服考试通过通知"
    content = (
        f"恭喜 {target['username']}！经管理员复审，你已通过"
        f"《望海服务器二周目审核问卷》，正式加入望海服务器，祝你游戏愉快！"
    )
    message_db.create_message(title, content, admin_uid, scope="user", target_uid=uid)
    _send_email(
        target["email"],
        f"[望海服务器] 入服考试通过 - {target['username']}",
        content,
        "zh",
    )


# ---------------------------------------------------------------------------
# 路由注册：按类拆分到 backend/api/*.py（只拆路由注册；
# 生命周期 / 全局异常处理 / 辅助逻辑均保留在本文件）。
#
# 顺序注意：auth 必须先于 user 注册——/api/user/me、/api/user/username_exists
# 等静态段不能被 /api/user/{uid} 的 int 参数路由抢先匹配（否则会 422）。
# 同一文件内（如 user.py 的 by_player_name 先于 /api/user/{uid}）同理。
# ---------------------------------------------------------------------------
from api.auth import router as auth_router
from api.avatar import router as avatar_router
from api.exam import router as exam_router
from api.message import router as message_router
from api.server import router as server_router
from api.site import router as site_router
from api.user import router as user_router

app.include_router(site_router)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(avatar_router)
app.include_router(message_router)
app.include_router(exam_router)
app.include_router(server_router)
