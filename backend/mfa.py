"""双重验证（MFA）核心逻辑。

两种验证方式：

* **验证器 App（TOTP）**：标准 RFC 6238，6 位数字 / 30 秒，微软 Authenticator、
  Google Authenticator 等均可通过「其他账户」扫码添加。二维码在后端本地生成，
  密钥不会经过任何第三方服务。
* **微软账号批准**：使用 Microsoft Entra ID（Azure AD）的设备码流程（Device
  Authorization Grant）。用户在 microsoft.com/devicelogin 输入设备码后，
  登录请求会推送到手机上的 Microsoft Authenticator，用户在 App 内批准
  （若租户启用了号码匹配，还需输入浏览器上显示的数字）。

本模块只负责协议与算法，HTTP 路由见 ``api/mfa.py``。
"""

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
import urllib.error
import urllib.parse
import urllib.request

from data import read_config

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

TOTP_DIGITS = 6
TOTP_PERIOD = 30
# 允许前后各一个时间步的时钟偏差（±30 秒）
TOTP_WINDOW = 1

RECOVERY_CODE_COUNT = 8
# 去掉 0/O、1/I 等易混淆字符
_RECOVERY_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"

# 设备码流程请求的权限：只需要读取基本身份信息（oid / 邮箱），不申请任何
# 邮件、文件等业务权限。
MS_SCOPE = "openid profile email"
MS_AUTHORITY = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0"

# 绑定 / 登录设备码挑战的存活时间（秒）。设备码本身通常 15 分钟过期，
# 这里保守取 10 分钟，避免长期占用内存。
CHALLENGE_TTL = 600

# 绑定挑战与登录二次验证挑战：challenge_id -> 上下文
_BIND_CHALLENGES: dict[str, dict] = {}
_LOGIN_CHALLENGES: dict[str, dict] = {}


class MfaError(Exception):
    """MFA 业务错误，携带稳定错误码（由路由层翻译成双语响应）。"""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


# ---------------------------------------------------------------------------
# TOTP（RFC 6238）
# ---------------------------------------------------------------------------

def generate_secret(nbytes: int = 20) -> str:
    """生成 base32 编码的 TOTP 密钥（默认 160 bit，与主流验证器一致）。"""
    return base64.b32encode(secrets.token_bytes(nbytes)).decode("ascii").rstrip("=")


def _decode_secret(secret: str) -> bytes:
    """把 base32 密钥解码为字节（自动补全 ``=`` 填充）。"""
    s = (secret or "").strip().upper().replace(" ", "")
    pad = "=" * (-len(s) % 8)
    try:
        return base64.b32decode(s + pad)
    except (ValueError, base64.binascii.Error) as exc:
        raise MfaError("mfa_code_invalid") from exc


def _hotp(secret: bytes, counter: int) -> str:
    """RFC 4226 HOTP：HMAC-SHA1 + 动态截断。"""
    digest = hmac.new(secret, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{value % (10 ** TOTP_DIGITS):0{TOTP_DIGITS}d}"


def totp_at(secret: str, at: float | None = None) -> str:
    """计算指定时刻（默认当前）的 TOTP 验证码。"""
    counter = int((at if at is not None else time.time()) // TOTP_PERIOD)
    return _hotp(_decode_secret(secret), counter)


def verify_totp(secret: str, code: str, last_step: int = 0) -> int | None:
    """校验 TOTP 验证码。

    允许 ±``TOTP_WINDOW`` 个时间步的偏差；为阻止同一验证码被重复使用，
    只接受时间步大于 ``last_step`` 的验证码。

    :return: 验证通过时返回命中的时间步（调用方应写回 ``mfa_last_step``）；
             失败返回 ``None``。
    """
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != TOTP_DIGITS:
        return None
    secret_bytes = _decode_secret(secret)
    current = int(time.time() // TOTP_PERIOD)
    for offset in range(-TOTP_WINDOW, TOTP_WINDOW + 1):
        step = current + offset
        if step <= last_step:
            continue
        if hmac.compare_digest(_hotp(secret_bytes, step), code):
            return step
    return None


def otpauth_uri(secret: str, account: str, issuer: str = "望海服务器") -> str:
    """生成验证器 App 可识别的 ``otpauth://`` 添加链接。"""
    label = urllib.parse.quote(f"{issuer}:{account}", safe="")
    params = urllib.parse.urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": TOTP_DIGITS,
            "period": TOTP_PERIOD,
        }
    )
    return f"otpauth://totp/{label}?{params}"


# ---------------------------------------------------------------------------
# 二维码（本地生成 SVG，密钥不离开服务器）
# ---------------------------------------------------------------------------

try:  # 缺少 qrcode 依赖时降级为仅展示密钥 / 链接，不影响其他功能
    import qrcode
except ImportError:  # pragma: no cover
    qrcode = None


def qr_svg(data: str, border: int = 2, size: int = 220) -> str:
    """把文本编码为二维码 SVG；依赖缺失时返回空字符串。"""
    if qrcode is None:
        return ""
    qr = qrcode.QRCode(border=border, box_size=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)
    parts = []
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                parts.append(f"M{x} {y}h1v1h-1z")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" '
        f'width="{size}" height="{size}" shape-rendering="crispEdges">'
        f'<rect width="{n}" height="{n}" fill="#ffffff"/>'
        f'<path d="{"".join(parts)}" fill="#111111"/></svg>'
    )


# ---------------------------------------------------------------------------
# 恢复码
# ---------------------------------------------------------------------------

def _normalize_recovery(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """生成一次性恢复码，形如 ``ABCDE-FGHJK``。"""
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def _hash_recovery(code: str) -> str:
    """恢复码哈希：沿用项目密码的加盐 SHA-256 方案（``<salt>$<hash>``）。"""
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}{_normalize_recovery(code)}".encode()).hexdigest()
    return f"{salt}${digest}"


def hash_recovery_codes(codes: list[str]) -> list[str]:
    return [_hash_recovery(c) for c in codes]


def match_recovery_code(stored: list[str], code: str) -> int | None:
    """在已存哈希列表中查找恢复码；命中返回其下标，否则返回 ``None``。"""
    normalized = _normalize_recovery(code)
    if not normalized:
        return None
    for index, item in enumerate(stored):
        try:
            salt, expected = item.split("$", 1)
        except ValueError:
            continue
        actual = hashlib.sha256(f"{salt}{normalized}".encode()).hexdigest()
        if hmac.compare_digest(actual, expected):
            return index
    return None


# ---------------------------------------------------------------------------
# 微软账号批准：Entra ID 设备码流程
# ---------------------------------------------------------------------------

def ms_config() -> dict:
    """读取 ``data/config.json`` 中的 ``microsoft`` 配置。"""
    return read_config().get("microsoft") or {}


def ms_configured() -> bool:
    """是否已完成 Entra ID 应用注册（至少配置了 client_id）。"""
    return bool((ms_config().get("client_id") or "").strip())


def _ms_endpoint(path: str) -> tuple[str, str]:
    tenant = (ms_config().get("tenant_id") or "common").strip() or "common"
    client_id = (ms_config().get("client_id") or "").strip()
    return MS_AUTHORITY.format(tenant=urllib.parse.quote(tenant)) + path, client_id


def _post_form_sync(url: str, form: dict) -> tuple[dict, int]:
    """发送 application/x-www-form-urlencoded 请求，返回 (JSON, HTTP 状态码)。

    Microsoft 的错误也以 JSON 返回（4xx），因此这里把错误体原样交给调用方。
    """
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8")), resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except ValueError:
            payload = {"error": "http_error", "error_description": body[:300]}
        return payload, exc.code
    except Exception as exc:  # 网络不可达 / 超时
        return {"error": "network_error", "error_description": f"{type(exc).__name__}: {exc}"}, 0


async def start_device_flow() -> dict:
    """发起设备码流程，返回 device_code / user_code / verification_uri 等。"""
    if not ms_configured():
        raise MfaError("mfa_ms_not_configured")
    url, client_id = _ms_endpoint("/devicecode")
    payload, status = await asyncio.to_thread(
        _post_form_sync, url, {"client_id": client_id, "scope": MS_SCOPE}
    )
    if status != 200 or not payload.get("device_code"):
        print(f"[mfa-ms] devicecode 失败: {payload}", flush=True)
        raise MfaError("mfa_ms_unavailable")
    return payload


def _decode_jwt_payload(token: str) -> dict:
    """解码 JWT 的 payload（不校验签名）。

    令牌是后端直接通过 TLS 从 Microsoft 令牌端点取得的，通道本身可信；
    这里仍校验 aud / iss / exp，防止串用其他应用的令牌。
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def _account_from_id_token(id_token: str, client_id: str) -> dict | None:
    """从 id_token 提取并校验微软账号信息；不合法返回 None。"""
    claims = _decode_jwt_payload(id_token)
    if not claims:
        return None
    if claims.get("aud") != client_id:
        return None
    if int(claims.get("exp") or 0) <= int(time.time()):
        return None
    if not str(claims.get("iss") or "").startswith("https://login.microsoftonline.com/"):
        return None
    oid = claims.get("oid") or claims.get("sub")
    if not oid:
        return None
    return {
        "oid": str(oid),
        "email": (
            claims.get("email")
            or claims.get("preferred_username")
            or claims.get("upn")
            or str(oid)
        ),
        "name": claims.get("name") or "",
        "tid": claims.get("tid") or "",
    }


async def poll_device_flow(device_code: str) -> dict:
    """轮询令牌端点。

    :return: ``{"status": "success", "account": {...}}``，
             或 ``{"status": "pending" / "slow_down" / "declined" / "expired" / "error"}``。
    """
    if not ms_configured():
        raise MfaError("mfa_ms_not_configured")
    url, client_id = _ms_endpoint("/token")
    payload, status = await asyncio.to_thread(
        _post_form_sync,
        url,
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": client_id,
            "device_code": device_code,
        },
    )
    if status == 200 and payload.get("id_token"):
        account = _account_from_id_token(payload["id_token"], client_id)
        if account is None:
            return {"status": "error", "error": "invalid_id_token"}
        return {"status": "success", "account": account}

    error = str(payload.get("error") or "")
    if error == "authorization_pending":
        return {"status": "pending"}
    if error == "slow_down":
        return {"status": "slow_down"}
    if error == "authorization_declined":
        return {"status": "declined"}
    if error in ("expired_token", "code_expired"):
        return {"status": "expired"}
    print(f"[mfa-ms] token 轮询失败: {payload}", flush=True)
    return {"status": "error", "error": error or "unknown"}


# ---------------------------------------------------------------------------
# 挑战状态（内存）
# ---------------------------------------------------------------------------

def _new_challenge_id() -> str:
    return secrets.token_urlsafe(24)


def _purge_challenges(store: dict) -> None:
    now = time.time()
    for key in [k for k, v in store.items() if now - v.get("created_at", 0) > CHALLENGE_TTL]:
        store.pop(key, None)


def create_bind_challenge(uid: int, device: dict) -> str:
    """登记一次「绑定微软账号」的设备码挑战。"""
    _purge_challenges(_BIND_CHALLENGES)
    challenge_id = _new_challenge_id()
    _BIND_CHALLENGES[challenge_id] = {
        "uid": uid,
        "device_code": device["device_code"],
        "created_at": time.time(),
        "expires_in": int(device.get("expires_in") or CHALLENGE_TTL),
        "interval": int(device.get("interval") or 5),
    }
    return challenge_id


def get_bind_challenge(challenge_id: str, uid: int) -> dict:
    """取出绑定挑战（校验归属）；无效时抛 ``mfa_ms_challenge_invalid``。"""
    _purge_challenges(_BIND_CHALLENGES)
    ctx = _BIND_CHALLENGES.get(challenge_id)
    if not ctx or ctx.get("uid") != uid:
        raise MfaError("mfa_ms_challenge_invalid")
    return ctx


def drop_bind_challenge(challenge_id: str) -> None:
    _BIND_CHALLENGES.pop(challenge_id, None)


def create_login_challenge(uid: int, device: dict) -> str:
    """登记一次「登录二次验证」的设备码挑战。"""
    _purge_challenges(_LOGIN_CHALLENGES)
    challenge_id = _new_challenge_id()
    _LOGIN_CHALLENGES[challenge_id] = {
        "uid": uid,
        "device_code": device["device_code"],
        "created_at": time.time(),
        "expires_in": int(device.get("expires_in") or CHALLENGE_TTL),
        "interval": int(device.get("interval") or 5),
    }
    return challenge_id


def get_login_challenge(challenge_id: str, uid: int) -> dict:
    _purge_challenges(_LOGIN_CHALLENGES)
    ctx = _LOGIN_CHALLENGES.get(challenge_id)
    if not ctx or ctx.get("uid") != uid:
        raise MfaError("mfa_ms_challenge_invalid")
    return ctx


def drop_login_challenge(challenge_id: str) -> None:
    _LOGIN_CHALLENGES.pop(challenge_id, None)
