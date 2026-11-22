"""工程管理路由：网页与游戏内 signup 插件共享同一份 `project.json`。

数据源是 signup 插件（经 mcdr2web 的 WS 桥接），本模块不写数据库：

- 浏览（列表 / 详情）公开；
- 发起需要 permission >= 3（创建者必然已绑定游戏账号）；
- 认领需要 permission >= 2，且所选 MC 玩家名属于当前用户；
- 完成需要发起者本人或 permission >= 3；
- 删除与插件逻辑一致：permission >= 4 可删任意状态；否则仅未认领时，
  permission >= 3 或发起者可删；
- 描述 / 备注仅发起者或 permission >= 3 可编辑；
- MCDR 离线时读接口回退 10s 缓存并标记 offline，写接口返回 503。
"""

import datetime
import threading
import time

from fastapi import APIRouter, Body, Depends

from main import (
    ERROR_STATUS,
    _error_response,
    get_current_user,
    user_info_db,
    ws_request_sync,
    ws_server,
)

router = APIRouter()

# 权限阈值（0=guest 1=user 2=player 3=admin 4=owner）
MEMBER_PERMISSION = 2
ADMIN_PERMISSION = 3
OWNER_PERMISSION = 4

# 工程列表缓存：10s；写操作后立即失效
PROJECT_CACHE_TTL = 10.0
MAX_NAME_LENGTH = 32
MAX_DESCRIPTION_LENGTH = 20_000
MAX_REMARK_LENGTH = 500

# WS 超时：沿用现有约定（读 3s / 写 10s）
READ_TIMEOUT = 3.0
WRITE_TIMEOUT = 10.0

# 离线日志限频（秒），避免每次请求都刷屏
OFFLINE_LOG_INTERVAL = 60.0

# 可由 mcdr2web 透传的业务错误码（其余视为桥接不可用）
PROJECT_ERROR_CODES = {
    "project_not_found",
    "project_exists",
    "project_name_invalid",
    "project_player_invalid",
    "project_already_claimed",
    "project_not_claimed",
    "project_completed",
    "project_unavailable",
}

_CACHE_LOCK = threading.Lock()
_PROJECT_CACHE: dict = {
    "items": None,
    "fetched_at": 0.0,
    "updated_at": "",
    "online": False,
}
_offline_log_at = 0.0


def _project_error(code: str):
    """构造工程相关的结构化双语错误响应。"""
    return _error_response(code, ERROR_STATUS.get(code, 400))


def _log_offline() -> None:
    """MCDR 工程桥接不可用时限频打印一条日志。"""
    global _offline_log_at
    now = time.monotonic()
    if now - _offline_log_at < OFFLINE_LOG_INTERVAL:
        return
    _offline_log_at = now
    print("[project] MCDR 工程桥接不可用，工程接口返回离线提示", flush=True)


def _call_project(command: str, data=None, timeout: float = READ_TIMEOUT):
    """调用 mcdr2web 的工程指令，返回 ``(data, error_code)``。"""
    if not ws_server.has_clients:
        _log_offline()
        return None, "project_unavailable"
    resp = ws_request_sync(command, data, timeout)
    if resp.get("success"):
        return resp.get("data"), None
    code = str(resp.get("data") or "").strip()
    if code in PROJECT_ERROR_CODES:
        return None, code
    _log_offline()
    return None, "project_unavailable"


def _cached_items() -> list[dict]:
    with _CACHE_LOCK:
        items = _PROJECT_CACHE["items"]
        return list(items) if isinstance(items, list) else []


def _cache_apply_project(project: dict) -> None:
    """把写操作返回的工程同步进列表缓存（离线时仍能读到最新数据）。"""
    with _CACHE_LOCK:
        items = _PROJECT_CACHE["items"]
        if not isinstance(items, list):
            return
        for index, existing in enumerate(items):
            if existing.get("name") == project.get("name"):
                items[index] = project
                break
        else:
            items.append(project)
        _PROJECT_CACHE["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")


def _cache_remove_project(name: str) -> None:
    """从列表缓存中移除已删除的工程。"""
    with _CACHE_LOCK:
        items = _PROJECT_CACHE["items"]
        if not isinstance(items, list):
            return
        _PROJECT_CACHE["items"] = [
            project for project in items if project.get("name") != name
        ]
        _PROJECT_CACHE["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")


def _get_project_items() -> tuple[list[dict], bool]:
    """读取工程列表，返回 ``(items, online)``；离线时回退缓存。"""
    now = time.monotonic()
    with _CACHE_LOCK:
        items = _PROJECT_CACHE["items"]
        if isinstance(items, list) and now - _PROJECT_CACHE["fetched_at"] < PROJECT_CACHE_TTL:
            return list(items), bool(_PROJECT_CACHE["online"])

    data, code = _call_project("project_list", {}, READ_TIMEOUT)
    projects = data.get("projects") if isinstance(data, dict) else None
    if code is not None or not isinstance(projects, list):
        with _CACHE_LOCK:
            _PROJECT_CACHE["online"] = False
        return _cached_items(), False

    clean = [project for project in projects if isinstance(project, dict)]
    with _CACHE_LOCK:
        _PROJECT_CACHE["items"] = clean
        _PROJECT_CACHE["fetched_at"] = time.monotonic()
        _PROJECT_CACHE["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        _PROJECT_CACHE["online"] = True
    return list(clean), True


def _get_project(name: str) -> tuple[dict | None, bool, str | None]:
    """按名称读取单个工程，返回 ``(project, online, error_code)``。"""
    data, code = _call_project("project_get", {"name": name}, READ_TIMEOUT)
    if code is None:
        project = data.get("project") if isinstance(data, dict) else None
        if isinstance(project, dict):
            return project, True, None
        return None, True, "project_unavailable"
    if code == "project_not_found":
        return None, True, "project_not_found"
    # 桥接不可用：回退缓存中的同名工程
    for project in _cached_items():
        if project.get("name") == name:
            return project, False, None
    return None, False, "project_unavailable"


def _resolve_uid(player_name: str) -> int | None:
    """把 MC 玩家名解析为网站 uid（主账号或小号）；解析不到返回 None。"""
    name = (player_name or "").strip()
    if not name:
        return None
    return user_info_db.get_uid_by_player_name(name)


def _user_player_names(uid: int) -> list[str]:
    """当前用户可用的 MC 玩家名（主账号在前，随后是小号）。"""
    info = user_info_db.get_user_info(uid) or {}
    names: list[str] = []
    main = str(info.get("player_name") or "").strip()
    if main:
        names.append(main)
    for alt in user_info_db.get_alt_accounts(uid):
        alt = str(alt).strip()
        if alt and alt not in names:
            names.append(alt)
    return names


def _is_creator(project: dict, user: dict | None) -> bool:
    """工程发起者是否为当前网站用户（按 MC 名解析 uid）。"""
    if user is None:
        return False
    creator = str(project.get("creator") or "").strip()
    if not creator:
        return False
    return _resolve_uid(creator) == user["uid"]


def _serialize_project(project: dict) -> dict:
    """工程对外的展示结构：补 uid、把认领者转为 {name, uid}。"""
    creator = str(project.get("creator") or "")
    claimants = []
    for name in project.get("claimants") or []:
        name = str(name)
        claimants.append({"name": name, "uid": _resolve_uid(name)})
    return {
        "name": str(project.get("name") or ""),
        "creator": creator,
        "creator_uid": _resolve_uid(creator),
        "status": str(project.get("status") or "unclaimed"),
        "claimants": claimants,
        "description": str(project.get("description") or ""),
        "remark": str(project.get("remark") or ""),
        "created_at": str(project.get("created_at") or ""),
        "updated_at": str(project.get("updated_at") or ""),
        "claimed_at": project.get("claimed_at"),
        "completed_at": project.get("completed_at"),
    }


def _viewer(project: dict, user: dict | None) -> dict:
    """当前用户对某个工程可执行的操作（与插件逻辑保持一致）。"""
    permission = int((user or {}).get("permission") or 0)
    status = str(project.get("status") or "unclaimed")
    is_creator = _is_creator(project, user)
    names = set(_user_player_names(user["uid"])) if user else set()
    claimed = {str(name) for name in (project.get("claimants") or [])}
    return {
        "is_creator": is_creator,
        "can_claim": bool(user)
        and permission >= MEMBER_PERMISSION
        and status in ("unclaimed", "claimed")
        and bool(names - claimed),
        "can_complete": bool(user)
        and status == "claimed"
        and (is_creator or permission >= ADMIN_PERMISSION),
        "can_delete": bool(user)
        and (
            permission >= OWNER_PERMISSION
            or (status == "unclaimed" and (permission >= ADMIN_PERMISSION or is_creator))
        ),
        "can_edit": bool(user) and (is_creator or permission >= ADMIN_PERMISSION),
    }


def _validate_name(value) -> tuple[str | None, object | None]:
    """校验工程名称；返回 ``(name, error_response)``。"""
    name = str(value or "").strip()
    if not name or any(ord(ch) < 32 for ch in name):
        return None, _project_error("project_name_invalid")
    if len(name) > MAX_NAME_LENGTH:
        return None, _project_error("project_name_too_large")
    return name, None


def _validate_player(user: dict, value) -> tuple[str | None, object | None]:
    """校验所选 MC 玩家名属于当前用户；为空时回退主账号。"""
    names = _user_player_names(user["uid"])
    if not names:
        return None, _error_response("no_main_account", ERROR_STATUS.get("no_main_account", 400))
    player = str(value or "").strip()
    if not player:
        player = names[0]
    if player not in names:
        return None, _project_error("project_player_invalid")
    return player, None


@router.get("/api/projects")
def project_list(user: dict | None = Depends(get_current_user)):
    """工程列表（公开）：状态计数 + 每项当前用户可执行的操作。"""
    projects, online = _get_project_items()
    items = []
    counts = {"all": 0, "unclaimed": 0, "claimed": 0, "completed": 0}
    for project in projects:
        item = _serialize_project(project)
        item["viewer"] = _viewer(project, user)
        items.append(item)
        counts["all"] += 1
        if item["status"] in counts:
            counts[item["status"]] += 1
    with _CACHE_LOCK:
        updated_at = _PROJECT_CACHE["updated_at"] or None
    return {
        "items": items,
        "counts": counts,
        "online": online,
        "stale": not online,
        "updated_at": updated_at,
    }


@router.get("/api/projects/detail")
def project_detail(name: str = "", user: dict | None = Depends(get_current_user)):
    """工程详情（公开）：离线时返回缓存并标记 stale。"""
    name = (name or "").strip()
    if not name:
        return _project_error("project_name_invalid")
    project, online, code = _get_project(name)
    if code is not None:
        return _project_error(code)
    return {
        "project": _serialize_project(project),
        "viewer": _viewer(project, user),
        "online": online,
        "stale": not online,
    }


@router.get("/api/projects/accounts")
def project_accounts(user: dict | None = Depends(get_current_user)):
    """当前用户可用于发起 / 认领的 MC 账号（主账号 + 小号）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    names = _user_player_names(user["uid"])
    accounts = [
        {"name": name, "primary": index == 0} for index, name in enumerate(names)
    ]
    return {"accounts": accounts, "default": names[0] if names else ""}


@router.post("/api/projects")
def project_create(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """发起工程：permission >= 3，创建者使用所选 MC 账号。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if int(user.get("permission") or 0) < ADMIN_PERMISSION:
        return _project_error("project_permission_denied")
    name, error = _validate_name(payload.get("name"))
    if error is not None:
        return error
    player, error = _validate_player(user, payload.get("player"))
    if error is not None:
        return error
    data, code = _call_project(
        "project_create", {"name": name, "creator": player}, WRITE_TIMEOUT
    )
    if code is not None:
        return _project_error(code)
    project = data.get("project") if isinstance(data, dict) else None
    if not isinstance(project, dict):
        return _project_error("project_unavailable")
    _cache_apply_project(project)
    return {
        "success": True,
        "project": _serialize_project(project),
        "viewer": _viewer(project, user),
    }


@router.post("/api/projects/claim")
def project_claim(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """认领工程：permission >= 2，同一 MC 玩家名不能重复认领。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if int(user.get("permission") or 0) < MEMBER_PERMISSION:
        return _project_error("project_permission_denied")
    name, error = _validate_name(payload.get("name"))
    if error is not None:
        return error
    player, error = _validate_player(user, payload.get("player"))
    if error is not None:
        return error
    data, code = _call_project(
        "project_claim", {"name": name, "player": player}, WRITE_TIMEOUT
    )
    if code is not None:
        return _project_error(code)
    project = data.get("project") if isinstance(data, dict) else None
    if not isinstance(project, dict):
        return _project_error("project_unavailable")
    _cache_apply_project(project)
    return {
        "success": True,
        "project": _serialize_project(project),
        "viewer": _viewer(project, user),
    }


@router.post("/api/projects/complete")
def project_complete(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """完成工程：发起者本人或 permission >= 3。"""
    if user is None:
        return _error_response("unauthorized", 401)
    name, error = _validate_name(payload.get("name"))
    if error is not None:
        return error
    project, _, code = _get_project(name)
    if code is not None:
        return _project_error(code)
    permission = int(user.get("permission") or 0)
    if not (_is_creator(project, user) or permission >= ADMIN_PERMISSION):
        return _project_error("project_permission_denied")
    data, code = _call_project("project_complete", {"name": name}, WRITE_TIMEOUT)
    if code is not None:
        return _project_error(code)
    updated = data.get("project") if isinstance(data, dict) else None
    if not isinstance(updated, dict):
        return _project_error("project_unavailable")
    _cache_apply_project(updated)
    return {
        "success": True,
        "project": _serialize_project(updated),
        "viewer": _viewer(updated, user),
    }


@router.delete("/api/projects")
def project_delete(name: str = "", user: dict | None = Depends(get_current_user)):
    """删除工程：permission >= 4 可删任意状态；否则仅未认领时（>= 3 或发起者）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    name = (name or "").strip()
    if not name:
        return _project_error("project_name_invalid")
    project, _, code = _get_project(name)
    if code is not None:
        return _project_error(code)
    permission = int(user.get("permission") or 0)
    if permission < OWNER_PERMISSION:
        allowed = permission >= ADMIN_PERMISSION or _is_creator(project, user)
        if not allowed or project.get("status") != "unclaimed":
            return _project_error("project_permission_denied")
    _, code = _call_project("project_delete", {"name": name}, WRITE_TIMEOUT)
    if code is not None:
        return _project_error(code)
    _cache_remove_project(name)
    return {"success": True}


@router.put("/api/projects/meta")
def project_update_meta(
    payload: dict = Body(...), user: dict | None = Depends(get_current_user)
):
    """更新工程描述（Markdown）/ 备注（纯文本）：发起者或 permission >= 3。"""
    if user is None:
        return _error_response("unauthorized", 401)
    name, error = _validate_name(payload.get("name"))
    if error is not None:
        return error
    project, _, code = _get_project(name)
    if code is not None:
        return _project_error(code)
    permission = int(user.get("permission") or 0)
    if not (_is_creator(project, user) or permission >= ADMIN_PERMISSION):
        return _project_error("project_permission_denied")

    description = payload.get("description")
    remark = payload.get("remark")
    if description is not None:
        if not isinstance(description, str):
            return _error_response("invalid_parameter", 422)
        if len(description) > MAX_DESCRIPTION_LENGTH:
            return _project_error("project_description_too_large")
    if remark is not None:
        if not isinstance(remark, str):
            return _error_response("invalid_parameter", 422)
        if len(remark) > MAX_REMARK_LENGTH:
            return _project_error("project_remark_too_large")

    data, code = _call_project(
        "project_update",
        {"name": name, "description": description, "remark": remark},
        WRITE_TIMEOUT,
    )
    if code is not None:
        return _project_error(code)
    updated = data.get("project") if isinstance(data, dict) else None
    if not isinstance(updated, dict):
        return _project_error("project_unavailable")
    _cache_apply_project(updated)
    return {
        "success": True,
        "project": _serialize_project(updated),
        "viewer": _viewer(updated, user),
    }
