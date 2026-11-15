"""用户认证路由：验证码 / 注册 / 登录 / 当前用户 / 解锁 / 保存资料。"""
import re
import secrets
import time
from datetime import date

from fastapi import APIRouter, Body, Depends

from data.main.database.user_database import UserNotFoundError

from main import (
    CODE_MAX_FAILURES,
    CODE_LOCK_SECONDS,
    CODE_TTL,
    EMAIL_RE,
    ERROR_STATUS,
    MC_NAME_RE,
    REGISTER_TICKETS,
    REGISTER_TICKET_TTL,
    SEND_COOLDOWN,
    USERNAME_RE,
    VERIFY_CODES,
    _clear_failures,
    _code_failures,
    _code_locked_until,
    _error_response,
    _find_by_identifier,
    _hash_password,
    _last_send_time,
    _public_user,
    _record_failure,
    _send_email,
    _verify_hcaptcha,
    _verify_password,
    check_user_active,
    create_token,
    get_current_user,
    user_db,
    user_info_db,
)

router = APIRouter()


@router.post("/api/user/send_code")
async def send_code(payload: dict = Body(...)):
    """向邮箱发送验证码；需先通过人机验证，防止被刷。"""
    hcaptcha_response = payload.get("hcaptcha_response") or ""
    if not await _verify_hcaptcha(hcaptcha_response):
        return _error_response("captcha_invalid", 400)
    email = (payload.get("email") or "").strip()
    if not EMAIL_RE.fullmatch(email):
        return _error_response("email_invalid", 400)

    now = time.time()
    if _code_locked_until.get(email, 0) > now:
        return _error_response("email_verify_locked", 429)
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
        # 注意：邮箱客户端摘要会折叠换行，验证码后紧跟的数字（如"5 分钟内有效"的 5）
        # 会与验证码粘连，让人误以为验证码多一位；因此用汉字"五"并加括号分隔。
        body = f"您的验证码是：{code}（五分钟内有效，请勿泄露）。\n"
    else:
        subject = "WHS Verification Code"
        body = f"Your verification code is: {code}.\n\nIt is valid for 5 minutes. Do not share it with anyone.\n"

    if not _send_email(email, subject, body, locale):
        # 发送失败：把刚写入内存的验证码与发送冷却一并回滚，允许用户立即重试
        VERIFY_CODES.pop(email, None)
        _last_send_time.pop(email, None)
        return _error_response("email_send_failed", 502)
    return {"success": True}


@router.get("/api/user/username_exists")
def username_exists(username: str = ""):
    """检查用户名是否已被占用。"""
    username = username.strip()
    if not USERNAME_RE.fullmatch(username):
        return _error_response("username_invalid", 400)
    return {"exists": user_db.get_user(username=username) is not None}


@router.get("/api/user/player_name_exists")
def player_name_exists(player_name: str = ""):
    """检查玩家名称（Minecraft 名称）是否已被占用。"""
    player_name = player_name.strip()
    if not USERNAME_RE.fullmatch(player_name):
        return _error_response("player_name_invalid", 400)
    return {"exists": user_info_db.player_name_exists(player_name)}


@router.post("/api/user/suggest_username")
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


@router.post("/api/user/register/email")
async def verify_register_email(payload: dict = Body(...)):
    """注册第一步：校验邮箱验证码，通过后在内存暂存一次性注册凭证（不写数据库）。

    验证码错误累计 5 次后锁定该邮箱 1 小时（发送与校验都会拒绝）。
    """
    email = (payload.get("email") or "").strip()
    code = (payload.get("code") or "").strip()

    if not EMAIL_RE.fullmatch(email):
        return _error_response("email_invalid", 400)

    now = time.time()
    if _code_locked_until.get(email, 0) > now:
        return _error_response("email_verify_locked", 429)
    if user_db.get_user(email=email) is not None:
        return _error_response("email_exists", 409)

    rec = VERIFY_CODES.get(email)
    if not rec or rec["exp"] < now or rec["code"] != code:
        failures = _code_failures.get(email, 0) + 1
        if failures >= CODE_MAX_FAILURES:
            _code_failures.pop(email, None)
            _code_locked_until[email] = now + CODE_LOCK_SECONDS
            VERIFY_CODES.pop(email, None)
            return _error_response("email_verify_locked", 429)
        _code_failures[email] = failures
        return _error_response("code_invalid", 400)

    # 验证通过：消费验证码、清除失败计数，签发一次性注册凭证（默认 10 分钟）
    VERIFY_CODES.pop(email, None)
    _code_failures.pop(email, None)
    _code_locked_until.pop(email, None)
    for old_ticket, info in list(REGISTER_TICKETS.items()):
        if info["exp"] < now:
            REGISTER_TICKETS.pop(old_ticket, None)
    ticket = secrets.token_urlsafe(32)
    REGISTER_TICKETS[ticket] = {"email": email, "exp": now + REGISTER_TICKET_TTL}
    return {"ticket": ticket, "email": email, "expires_in": REGISTER_TICKET_TTL}


@router.post("/api/user/register")
async def register(payload: dict = Body(...)):
    """注册第二步：用第一步签发的凭证 + username + password 创建账号。

    email 取自凭证（第一步已校验验证码）；创建成功才消费凭证，
    用户名冲突等失败时凭证保留，便于前端「推荐用户名」后重试。
    """
    ticket = (payload.get("ticket") or "").strip()
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    rec = REGISTER_TICKETS.get(ticket)
    if rec is None or rec["exp"] < time.time():
        REGISTER_TICKETS.pop(ticket, None)
        return _error_response("register_ticket_invalid", 400)
    if not USERNAME_RE.fullmatch(username):
        return _error_response("username_invalid", 400)
    if not re.fullmatch(r"[0-9a-f]{64}", password):
        return _error_response("password_invalid", 400)

    # 注册时不再自动注入 fullname（留空，之后在用户设置里填）
    # 重复邮箱 / 重复用户名会抛 EmailExistsError / UsernameExistsError，由异常处理器统一翻译
    email = rec["email"]
    uid = user_db.create_user(username, email, "", _hash_password(password))
    user_info_db.set_user_info(uid)  # 预建一行扩展信息（性别/生日默认为空）
    REGISTER_TICKETS.pop(ticket, None)
    return {"uid": uid, "token": create_token(uid)}


@router.post("/api/user/login")
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
        err = check_user_active(user)
        if err:
            return _error_response(err, ERROR_STATUS.get(err, 403))
        rec = VERIFY_CODES.get(identifier)
        if not rec or rec["exp"] < time.time() or rec["code"] != code:
            if _record_failure(user["uid"], "code"):
                return _error_response("account_locked", 403)
            return _error_response("code_invalid", 400)
        VERIFY_CODES.pop(identifier, None)
    elif password is not None:
        # 账密模式：email / UID / username（不填验证码；人机验证仅在获取验证码时需要）
        user = _find_by_identifier(identifier)
        if user is None:
            return _error_response("user_not_found", 404)
        err = check_user_active(user)
        if err:
            return _error_response(err, ERROR_STATUS.get(err, 403))
        if not _verify_password(user["password"], password):
            if _record_failure(user["uid"], "password"):
                return _error_response("account_locked", 403)
            return _error_response("invalid_credentials", 401)
    else:
        return _error_response("invalid_credentials", 401)

    _clear_failures(user["uid"])
    return {"token": create_token(user["uid"]), "user": _public_user(user)}


@router.get("/api/user/me")
def me(user: dict | None = Depends(get_current_user)):
    """返回当前登录用户（供前端刷新头像/用户态）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    return _public_user(user)


@router.post("/api/user/{uid}/unlock")
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


@router.post("/api/user/{uid}/info")
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

    # 真实日期 + 不能是未来：只填到年时校验年份不超过今年，
    # 年月日都填时按真实日历校验（如 2 月 30 日非法）。
    today = date.today()
    if year is not None:
        if year > today.year:
            return _error_response("birthday_invalid", 400)
        if month is not None and day is not None:
            try:
                birthday = date(year, month, day)
            except ValueError:
                return _error_response("birthday_invalid", 400)
            if birthday > today:
                return _error_response("birthday_invalid", 400)

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
            if not MC_NAME_RE.fullmatch(player_name):
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
