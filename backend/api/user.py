"""用户主页 / 关注 / 简介 / 设置 / 密码 / 注销 / 管理员路由。"""
import re
import time
from pathlib import Path

from fastapi import APIRouter, Body, Depends
from fastapi.responses import RedirectResponse

from data.main.database.user_database import UserNotFoundError

from main import (
    EMAIL_RE,
    USERNAME_RE,
    VERIFY_CODES,
    AVATAR_DIR,
    _clear_failures,
    _error_response,
    _hash_password,
    _verify_password,
    add_player_whitelist,
    get_current_user,
    remove_player_whitelist,
    remove_user_whitelist,
    user_db,
    user_info_db,
)

router = APIRouter()


@router.get("/api/user/by_player_name/{player_name}")
def user_by_player_name(player_name: str):
    """按玩家名（player_name）查找用户，301 跳转到其主页路由 /user/{uid}。

    注意：查找字段是 user_info 表的 player_name（Minecraft 名称），
    而非 username / fullname。前端用该接口实现"成员主页跳转"。
    必须定义在 /api/user/{uid} 之前，否则会被其 int 参数路由抢先匹配。
    """
    player_name = player_name.strip()
    if not USERNAME_RE.fullmatch(player_name):
        return _error_response("player_name_invalid", 400)
    uid = user_info_db.get_uid_by_player_name(player_name)
    if uid is None:
        return _error_response("user_not_found", 404)
    return RedirectResponse(url=f"/user/{uid}", status_code=301)


@router.get("/api/user/{uid}")
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
    # 仅本人或管理员可见的敏感字段（供设置页 / 管理员代管他人设置使用）
    if is_self or (user is not None and (user.get("permission") or 0) >= 3):
        data["email"] = target["email"]
        data["permission"] = target.get("permission", 1)
        data["locked"] = bool(target.get("locked"))
        data["banned"] = bool(target.get("banned"))
    return data


@router.post("/api/user/{uid}/follow")
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


@router.post("/api/user/{uid}/unfollow")
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


@router.post("/api/user/{uid}/profile")
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


@router.post("/api/user/{uid}/email")
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


@router.post("/api/user/password_reset_verify")
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


@router.post("/api/user/password_reset")
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


@router.post("/api/user/{uid}/password_verify")
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


@router.post("/api/user/{uid}/password")
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


@router.post("/api/user/{uid}/cancel")
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


@router.post("/api/user/{uid}/ban")
def set_user_banned(uid: int, payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """封禁 / 解封用户；仅管理员，且只能封禁权限【严格低于自己】的用户（同级及以上不可封禁）。"""
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
    # 封禁即移除该用户全部白名单关联（主账号 + 小号）；解封不自动加回
    if banned:
        remove_user_whitelist(uid)
    return {"success": True, "banned": banned}


@router.post("/api/user/{uid}/permission")
def set_user_permission(uid: int, payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """设置用户权限等级；仅管理员，不能改自己。

    权限判断（与封禁略有差异）：改权限允许操作【同级 / 下级】（仅禁止高于自己），
    且新权限值最高等于自己（不能把用户设置成自己的上级）。
    """
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    if uid == user["uid"]:
        return _error_response("cannot_change_own_permission", 400)
    target = user_db.get_user(uid=uid)
    if target is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")
    # 权限判断（改权限）：仅禁止操作权限【高于自己】的用户（同级 / 下级均可操作）
    if (user.get("permission") or 0) < (target.get("permission") or 0):
        return _error_response("cannot_modify_higher_permission", 403)
    permission = payload.get("permission")
    if not isinstance(permission, int) or isinstance(permission, bool) or not (0 <= permission <= 4):
        return _error_response("invalid_permission", 400)
    # 新权限值判断：不能把用户设置得高于自己的权限（最高等于自己），防止下级造出上级
    if permission > (user.get("permission") or 0):
        return _error_response("new_permission_higher", 400)
    user_db.set_permission(uid, permission)
    return {"success": True, "permission": permission}


@router.get("/api/admin/users")
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
# 粉丝 / 关注列表（公开，供用户页悬浮窗展示）
# ---------------------------------------------------------------------------

def _build_follow_user(u: dict) -> dict:
    """粉丝/关注列表条目：对外暴露的用户摘要。"""
    return {
        "uid": u["uid"],
        "username": u["username"],
        "fullname": u["fullname"],
        "avatar": u.get("avatar"),
    }


def _list_follow_uids(uid: int, kind: str) -> list[dict]:
    """按 kind（followers/followings）返回用户摘要列表。"""
    uids = (
        user_info_db.get_followers(uid)
        if kind == "followers"
        else user_info_db.get_followings(uid)
    )
    users = []
    for f_uid in uids:
        u = user_db.get_user(uid=f_uid)
        if u is not None:
            users.append(_build_follow_user(u))
    return users


@router.get("/api/user/{uid}/followers")
def user_followers(uid: int):
    """关注该用户的用户列表（公开）。"""
    if user_db.get_user(uid=uid) is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")
    return {"users": _list_follow_uids(uid, "followers")}


@router.get("/api/user/{uid}/followings")
def user_followings(uid: int):
    """该用户关注的用户列表（公开）。"""
    if user_db.get_user(uid=uid) is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")
    return {"users": _list_follow_uids(uid, "followings")}


# ---------------------------------------------------------------------------
# 游戏账户管理：主账号(player_name) + 小号(alt_accounts) + 正版标签(premium_flags)
# ---------------------------------------------------------------------------

def _build_accounts(uid: int) -> dict:
    """组装某用户的游戏账户数据（主账号 + 小号 + 正版标签）。"""
    info = user_info_db.get_user_info(uid) or {}
    player_name = info.get("player_name") or ""
    flags = user_info_db.get_premium_flags(uid)
    alts = user_info_db.get_alt_accounts(uid)
    return {
        "player_name": player_name,
        "premium": flags.get(player_name, ""),  # 主账号正版标签（未设置为空）
        "alts": [{"name": n, "premium": flags.get(n, "")} for n in alts],
        "max_alts": 2,
    }


def _require_self_or_admin(uid: int, user: dict | None):
    """本人或管理员校验；不通过时返回错误响应，通过返回 None。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if user["uid"] != uid and (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    if user_db.get_user(uid=uid) is None:
        raise UserNotFoundError(f"uid={uid} 的用户不存在")
    return None


@router.get("/api/user/{uid}/accounts")
def user_accounts(uid: int, user: dict | None = Depends(get_current_user)):
    """查询游戏账户（主账号 / 小号 / 各自正版标签）；仅本人或管理员。"""
    err = _require_self_or_admin(uid, user)
    if err is not None:
        return err
    return _build_accounts(uid)


@router.post("/api/user/{uid}/premium")
def set_main_premium(uid: int, payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """修改主账号的正版状态；仅本人或管理员。"""
    err = _require_self_or_admin(uid, user)
    if err is not None:
        return err
    info = user_info_db.get_user_info(uid) or {}
    player_name = info.get("player_name") or ""
    if not player_name:
        return _error_response("no_main_account", 400)
    premium = payload.get("premium")
    if premium not in ("premium", "offline"):
        return _error_response("premium_invalid", 400)
    user_info_db.set_premium_flag(uid, player_name, premium)
    return {"success": True, "premium": premium}


@router.post("/api/user/{uid}/alts")
def add_alt_account(uid: int, payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """添加小号（最多两个；全局查重：不得与其它用户的主账号/小号重复）；仅本人或管理员。"""
    err = _require_self_or_admin(uid, user)
    if err is not None:
        return err
    name = str(payload.get("name") or "").strip()
    premium = payload.get("premium")
    if not USERNAME_RE.fullmatch(name):
        return _error_response("player_name_invalid", 400)
    if premium not in ("premium", "offline"):
        return _error_response("premium_invalid", 400)
    info = user_info_db.get_user_info(uid) or {}
    player_name = info.get("player_name") or ""
    if not player_name:
        return _error_response("no_main_account", 400)
    # 本用户内：不得与主账号或已有小号重复（重复检查优先于数量上限，便于提示）
    if name == player_name or name in user_info_db.get_alt_accounts(uid):
        return _error_response("player_name_exists", 409)
    # 全局查重：不得与其它用户的主账号/小号重复
    if user_info_db.account_name_taken_by_other(uid, name):
        return _error_response("player_name_exists", 409)
    if len(user_info_db.get_alt_accounts(uid)) >= 2:
        return _error_response("alt_accounts_full", 400)
    user_info_db.add_alt_account(uid, name, premium)
    # 注册小号自动加入游戏服务器白名单（幂等；失败仅记日志，不影响注册结果）
    add_player_whitelist(name)
    return {"success": True, "accounts": _build_accounts(uid)}


@router.delete("/api/user/{uid}/alts/{alt_name}")
def remove_alt_account(uid: int, alt_name: str, user: dict | None = Depends(get_current_user)):
    """注销小号（主账号不可注销）；仅本人或管理员。"""
    err = _require_self_or_admin(uid, user)
    if err is not None:
        return err
    alt_name = alt_name.strip()
    if not USERNAME_RE.fullmatch(alt_name):
        return _error_response("player_name_invalid", 400)
    removed = user_info_db.remove_alt_account(uid, alt_name)
    # 注销小号自动移除其白名单（幂等；失败仅记日志）
    if removed:
        remove_player_whitelist(alt_name)
    return {"success": True, "removed": removed, "accounts": _build_accounts(uid)}
