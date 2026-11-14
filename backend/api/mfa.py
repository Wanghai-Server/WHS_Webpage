"""双重验证（MFA）路由：设置 / 绑定 / 登录二次验证。

两种方式：
* TOTP 验证器 App（微软 Authenticator、Google Authenticator 等「其他账户」扫码）；
* 微软账号批准（Entra ID 设备码流程，手机上在 Microsoft Authenticator 内批准）。

所有加密与凭据存储沿用项目原有方案：密码为「前端 SHA-256 + 后端加盐 SHA-256」，
令牌为项目自带的 HMAC-SHA256 轻量令牌；TOTP 只在校验时使用共享密钥，
密钥与恢复码哈希均不出现在任何对外响应中。
"""

import time

from fastapi import APIRouter, Body, Depends

from main import (
    ERROR_STATUS,
    _error_response,
    _public_user,
    _record_failure,
    check_user_active,
    consume_mfa_token,
    create_token,
    get_current_user,
    user_db,
    verify_mfa_token,
)
import mfa
from mfa import MfaError

router = APIRouter()


def _err(code: str):
    """把 MFA 错误码翻译成项目统一的结构化双语响应。"""
    return _error_response(code, ERROR_STATUS.get(code, 400))


def _methods(uid: int) -> dict:
    """返回该用户当前可用的验证方式。"""
    data = user_db.get_mfa(uid)
    return {
        "totp": bool(data.get("mfa_totp_confirmed")),
        "microsoft": bool(data.get("mfa_ms_confirmed")) and mfa.ms_configured(),
    }


def _proof_ok(uid: int, code: str, mode: str = "auto") -> bool:
    """校验一次「敏感操作」的凭证：TOTP 验证码或恢复码（恢复码一次性）。

    失败时会计入项目的失败次数，连续错误同样触发账号锁定。
    """
    data = user_db.get_mfa(uid)
    secret = data.get("mfa_totp_secret")

    if mode in ("auto", "totp") and data.get("mfa_totp_confirmed") and secret:
        step = mfa.verify_totp(secret, code, int(data.get("mfa_last_step") or 0))
        if step is not None:
            user_db.set_mfa_last_step(uid, step)
            return True
        if mode == "totp":
            _record_failure(uid, "code")
            return False

    if mode in ("auto", "recovery"):
        stored = user_db.get_recovery(uid)
        index = mfa.match_recovery_code(stored, code)
        if index is not None:
            stored.pop(index)
            user_db.set_recovery(uid, stored)
            return True

    _record_failure(uid, "code")
    return False


def _issue_session(user: dict) -> dict:
    return {"token": create_token(user["uid"]), "user": _public_user(user)}


def _mfa_user(mfa_token: str):
    """解析 MFA 一次性令牌并返回 (payload, user)。"""
    payload = verify_mfa_token(mfa_token)
    if payload is None:
        return None, None
    user = user_db.get_user(uid=payload.get("uid"))
    if user is None:
        return None, None
    if check_user_active(user):
        return None, None
    return payload, user


def _device_public(device: dict) -> dict:
    """设备码响应中对外可见的部分（不含 device_code）。"""
    return {
        "user_code": device.get("user_code", ""),
        "verification_uri": device.get("verification_uri", ""),
        "expires_in": int(device.get("expires_in") or 0),
        "interval": int(device.get("interval") or 5),
        "message": device.get("message", ""),
    }


# ---------------------------------------------------------------------------
# 状态
# ---------------------------------------------------------------------------

@router.get("/api/user/mfa")
def mfa_status(user: dict | None = Depends(get_current_user)):
    """当前用户的双重验证状态。"""
    if user is None:
        return _err("unauthorized")
    data = user_db.get_mfa(user["uid"])
    return {
        "totp_enabled": bool(data.get("mfa_totp_confirmed")),
        "ms_enabled": bool(data.get("mfa_ms_confirmed")),
        "ms_email": data.get("mfa_ms_email") or "",
        "ms_available": mfa.ms_configured(),
        "recovery_remaining": len(user_db.get_recovery(user["uid"])),
    }


# ---------------------------------------------------------------------------
# 验证器 App（TOTP）
# ---------------------------------------------------------------------------

@router.post("/api/user/mfa/totp/setup")
async def totp_setup(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """生成新的 TOTP 密钥并返回二维码（密钥在首次验证前不生效）。"""
    if user is None:
        return _err("unauthorized")
    uid = user["uid"]
    data = user_db.get_mfa(uid)
    # 已启用的账号不允许直接覆盖密钥：必须先证明持有当前验证器
    if data.get("mfa_totp_confirmed") and not _proof_ok(uid, payload.get("code") or ""):
        return _err("mfa_code_invalid")

    secret = mfa.generate_secret()
    user_db.set_totp_secret(uid, secret, confirmed=False)
    account = user.get("username") or user.get("email") or str(uid)
    uri = mfa.otpauth_uri(secret, account)
    return {
        "secret": secret,
        "otpauth_uri": uri,
        "qr_svg": mfa.qr_svg(uri),
    }


@router.post("/api/user/mfa/totp/enable")
def totp_enable(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """用验证器 App 生成的 6 位码确认启用，并返回一次性恢复码。"""
    if user is None:
        return _err("unauthorized")
    uid = user["uid"]
    data = user_db.get_mfa(uid)
    secret = data.get("mfa_totp_secret")
    if data.get("mfa_totp_confirmed") or not secret:
        return _err("mfa_not_enabled")

    step = mfa.verify_totp(secret, payload.get("code") or "")
    if step is None:
        if _record_failure(uid, "code"):
            return _err("account_locked")
        return _err("mfa_code_invalid")

    user_db.confirm_totp(uid)
    user_db.set_mfa_last_step(uid, step)

    codes = mfa.generate_recovery_codes()
    user_db.set_recovery(uid, mfa.hash_recovery_codes(codes))
    return {"success": True, "recovery_codes": codes}


@router.post("/api/user/mfa/recovery/regenerate")
def recovery_regenerate(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """重新生成恢复码（需要当前的 TOTP 验证码或一枚未使用的恢复码）。"""
    if user is None:
        return _err("unauthorized")
    uid = user["uid"]
    methods = _methods(uid)
    if not methods["totp"] and not methods["microsoft"]:
        return _err("mfa_not_enabled")
    if not _proof_ok(uid, payload.get("code") or "", payload.get("mode") or "auto"):
        return _err("mfa_code_invalid")

    codes = mfa.generate_recovery_codes()
    user_db.set_recovery(uid, mfa.hash_recovery_codes(codes))
    return {"success": True, "recovery_codes": codes}


@router.post("/api/user/mfa/totp/disable")
def totp_disable(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """关闭验证器 App 验证（需要当前验证码或恢复码）。"""
    if user is None:
        return _err("unauthorized")
    uid = user["uid"]
    if not user_db.get_mfa(uid).get("mfa_totp_confirmed"):
        return _err("mfa_not_enabled")
    if not _proof_ok(uid, payload.get("code") or "", payload.get("mode") or "auto"):
        return _err("mfa_code_invalid")

    user_db.clear_totp(uid)
    _clear_recovery_if_unused(uid)
    return {"success": True}


# ---------------------------------------------------------------------------
# 微软账号批准（Entra ID 设备码流程）
# ---------------------------------------------------------------------------

@router.post("/api/user/mfa/ms/bind/start")
async def ms_bind_start(user: dict | None = Depends(get_current_user)):
    """发起绑定微软账号的设备码流程。"""
    if user is None:
        return _err("unauthorized")
    try:
        device = await mfa.start_device_flow()
    except MfaError as exc:
        return _err(exc.code)
    challenge_id = mfa.create_bind_challenge(user["uid"], device)
    return {"challenge_id": challenge_id, **_device_public(device)}


@router.post("/api/user/mfa/ms/bind/poll")
async def ms_bind_poll(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """轮询绑定结果；批准后把微软账号与本地账号绑定。"""
    if user is None:
        return _err("unauthorized")
    uid = user["uid"]
    challenge_id = (payload.get("challenge_id") or "").strip()
    try:
        ctx = mfa.get_bind_challenge(challenge_id, uid)
        result = await mfa.poll_device_flow(ctx["device_code"])
    except MfaError as exc:
        return _err(exc.code)

    status = result.get("status")
    if status != "success":
        if status in ("expired", "declined", "error"):
            mfa.drop_bind_challenge(challenge_id)
        return {"status": status}

    account = result["account"]
    user_db.set_ms_account(uid, account["oid"], account["email"], confirmed=True)
    mfa.drop_bind_challenge(challenge_id)

    # 首次启用双重验证时顺带发放恢复码；已有恢复码则保持原样
    codes: list[str] = []
    if not user_db.get_recovery(uid):
        codes = mfa.generate_recovery_codes()
        user_db.set_recovery(uid, mfa.hash_recovery_codes(codes))
    return {"status": "success", "email": account["email"], "recovery_codes": codes}


@router.post("/api/user/mfa/ms/disable")
def ms_disable(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """解除微软账号绑定。若同时启用了验证器 App，则需要验证码确认。"""
    if user is None:
        return _err("unauthorized")
    uid = user["uid"]
    data = user_db.get_mfa(uid)
    if not data.get("mfa_ms_confirmed"):
        return _err("mfa_not_enabled")
    if data.get("mfa_totp_confirmed"):
        if not _proof_ok(uid, payload.get("code") or "", payload.get("mode") or "auto"):
            return _err("mfa_code_invalid")

    user_db.clear_ms(uid)
    _clear_recovery_if_unused(uid)
    return {"success": True}


def _clear_recovery_if_unused(uid: int) -> None:
    """当两种验证方式都关闭时，一并清除恢复码（避免残留可用凭据）。"""
    data = user_db.get_mfa(uid)
    if not data.get("mfa_totp_confirmed") and not data.get("mfa_ms_confirmed"):
        user_db.set_recovery(uid, [])


# ---------------------------------------------------------------------------
# 登录二次验证（使用登录接口返回的短期 mfa_token，不依赖登录态）
# ---------------------------------------------------------------------------

@router.post("/api/user/mfa/verify")
def mfa_verify(payload: dict = Body(...)):
    """用验证器 App 的 6 位码或恢复码完成登录二次验证。"""
    token = payload.get("mfa_token") or ""
    _, user = _mfa_user(token)
    if user is None:
        return _err("mfa_token_invalid")
    uid = user["uid"]
    methods = _methods(uid)
    mode = payload.get("mode") or "totp"
    code = payload.get("code") or ""

    if mode == "recovery":
        if not _proof_ok(uid, code, "recovery"):
            return _err("mfa_recovery_invalid")
    elif mode == "totp":
        if not methods["totp"]:
            return _err("mfa_not_enabled")
        if not _proof_ok(uid, code, "totp"):
            return _err("mfa_code_invalid")
    else:
        return _err("mfa_code_invalid")

    if consume_mfa_token(token) is None:
        return _err("mfa_token_invalid")
    return _issue_session(user)


@router.post("/api/user/mfa/ms/login/start")
async def ms_login_start(payload: dict = Body(...)):
    """登录时发起微软账号批准（设备码流程）。"""
    token = payload.get("mfa_token") or ""
    _, user = _mfa_user(token)
    if user is None:
        return _err("mfa_token_invalid")
    if not _methods(user["uid"])["microsoft"]:
        return _err("mfa_not_enabled")
    try:
        device = await mfa.start_device_flow()
    except MfaError as exc:
        return _err(exc.code)
    challenge_id = mfa.create_login_challenge(user["uid"], device)
    return {"challenge_id": challenge_id, **_device_public(device)}


@router.post("/api/user/mfa/ms/login/poll")
async def ms_login_poll(payload: dict = Body(...)):
    """轮询微软账号批准结果；批准且账号匹配时签发登录令牌。"""
    token = payload.get("mfa_token") or ""
    _, user = _mfa_user(token)
    if user is None:
        return _err("mfa_token_invalid")
    uid = user["uid"]
    challenge_id = (payload.get("challenge_id") or "").strip()
    try:
        ctx = mfa.get_login_challenge(challenge_id, uid)
        result = await mfa.poll_device_flow(ctx["device_code"])
    except MfaError as exc:
        return _err(exc.code)

    status = result.get("status")
    if status != "success":
        if status in ("expired", "declined", "error"):
            mfa.drop_login_challenge(challenge_id)
        return {"status": status}

    account = result["account"]
    bound_oid = user_db.get_mfa(uid).get("mfa_ms_oid")
    if not bound_oid or account["oid"] != bound_oid:
        mfa.drop_login_challenge(challenge_id)
        return _err("mfa_ms_account_mismatch")

    if consume_mfa_token(token) is None:
        return _err("mfa_token_invalid")
    mfa.drop_login_challenge(challenge_id)
    return {"status": "success", "email": account["email"], **_issue_session(user)}
