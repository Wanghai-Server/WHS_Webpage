import asyncio
import base64
import hashlib
import hmac
import json
import re
import secrets
import sys
import time
import urllib.parse
import urllib.request
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, Depends, FastAPI, File, Header, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

# 将项目根目录加入 sys.path，以便导入与 backend/ 同级的 data 包。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data import read_config
from data.main.database.user_database import (
    ERROR_MESSAGES as USER_DB_ERROR_MESSAGES,
    UserDatabase,
    UserDatabaseError,
    UserNotFoundError,
)

# 用户数据库实例：随服务启动连接、随服务关闭释放。
user_db = UserDatabase()

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

# 与数据层一致：邮箱 / 密码格式。
EMAIL_RE = re.compile(r"[a-zA-Z0-9_@.-]+")
PASSWORD_RE = re.compile(r"^[\x00-\x7f]+$")

# 邮箱验证码（mock）：内存存储 email -> {code, exp}，TTL 5 分钟。
VERIFY_CODES = {}
CODE_TTL = 300


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
    return user_db.get_user(uid=payload.get("uid"))


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
    except Exception:
        return False


async def _verify_hcaptcha(response: str) -> bool:
    return await asyncio.to_thread(_verify_hcaptcha_sync, response)


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
}

# 错误码 -> HTTP 状态码。
ERROR_STATUS: dict[str, int] = {
    "username_invalid": 400,
    "email_invalid": 400,
    "password_invalid": 400,
    "username_exists": 409,
    "email_exists": 409,
    "user_not_found": 404,
    "avatar_too_large": 413,
    "avatar_unsupported_type": 400,
    "avatar_not_found": 404,
    "code_invalid": 400,
    "captcha_invalid": 400,
    "invalid_credentials": 401,
    "unauthorized": 401,
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
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    yield
    user_db.close()


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
    return {"title_suffix": read_config().get("title_suffix", {})}


# ---------------------------------------------------------------------------
# 用户认证
# ---------------------------------------------------------------------------

@app.post("/api/user/send_code")
def send_code(payload: dict = Body(...)):
    """向邮箱发送验证码（mock：打印到日志并回传 dev_code）。"""
    email = (payload.get("email") or "").strip()
    if not EMAIL_RE.fullmatch(email):
        return _error_response("email_invalid", 400)
    code = f"{uuid.uuid4().int % 1000000:06d}"
    VERIFY_CODES[email] = {"code": code, "exp": time.time() + CODE_TTL}
    print(f"[verify-code] {email} -> {code}", flush=True)
    return {"dev_code": code}


@app.post("/api/user/register")
async def register(payload: dict = Body(...)):
    """注册：email + 验证码 + password + hCaptcha，自动生成 username。"""
    email = (payload.get("email") or "").strip()
    code = (payload.get("code") or "").strip()
    password = payload.get("password") or ""
    hcaptcha_response = payload.get("hcaptcha_response") or ""

    if not EMAIL_RE.fullmatch(email):
        return _error_response("email_invalid", 400)
    if not re.fullmatch(r"[0-9a-f]{64}", password):
        return _error_response("password_invalid", 400)
    if not await _verify_hcaptcha(hcaptcha_response):
        return _error_response("captcha_invalid", 400)
    rec = VERIFY_CODES.get(email)
    if not rec or rec["exp"] < time.time() or rec["code"] != code:
        return _error_response("code_invalid", 400)

    username = _derive_username(email)
    fullname = email.split("@")[0]
    # 重复邮箱会抛 EmailExistsError，由异常处理器统一翻译
    uid = user_db.create_user(username, email, fullname, _hash_password(password))
    VERIFY_CODES.pop(email, None)
    return {"uid": uid, "token": create_token(uid)}


@app.post("/api/user/login")
async def login(payload: dict = Body(...)):
    """登录：账密模式（identifier + password）或邮箱验证码模式（email + code）。"""
    hcaptcha_response = payload.get("hcaptcha_response") or ""
    if not await _verify_hcaptcha(hcaptcha_response):
        return _error_response("captcha_invalid", 400)
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
        rec = VERIFY_CODES.get(identifier)
        if not rec or rec["exp"] < time.time() or rec["code"] != code:
            return _error_response("code_invalid", 400)
        VERIFY_CODES.pop(identifier, None)
    elif password is not None:
        # 账密模式：email / UID / username
        user = _find_by_identifier(identifier)
        if user is None:
            return _error_response("user_not_found", 404)
        if not _verify_password(user["password"], password):
            return _error_response("invalid_credentials", 401)
    else:
        return _error_response("invalid_credentials", 401)

    return {"token": create_token(user["uid"]), "user": _public_user(user)}


@app.get("/api/user/me")
def me(user: dict | None = Depends(get_current_user)):
    """返回当前登录用户（供前端刷新头像/用户态）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    return _public_user(user)


# ---------------------------------------------------------------------------
# 头像
# ---------------------------------------------------------------------------

@app.post("/api/user/{uid}/avatar")
async def upload_avatar(uid: int, file: UploadFile = File(...)):
    """上传头像：校验类型/大小，落盘并更新 users.avatar。"""
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

@app.get("/api/message/{user_id}")
def user_message(user_id: str):
    ...
