"""轨交路线图路由：公开读取 + 管理员提交 / 回退 / 校验。

- 读取（当前版本、历史列表）公开，与 BlueMap 的成员门槛无关；
- 提交、回退、校验需要 permission >= 3；
- 冲突时返回 409 与冲突清单；`force` 强制并入只允许 permission >= 4。

数据文件 `data/transit.yml` 不入库，由 `main.lifespan` 启动时自动创建（见 data/transit.py）。
"""

from fastapi import APIRouter, Body, Header
from fastapi.responses import JSONResponse

from data import read_config
from data.transit import (
    TRANSIT_PATH,
    TransitConflictError,
    TransitConfigError,
    diff_versions,
    load_current,
    read_store,
    rollback,
    submit,
    validate_data,
)
from main import ERROR_MESSAGES, get_current_user

router = APIRouter()

_EDIT_PERMISSION = 3
_FORCE_PERMISSION = 4

# 当前版本 payload 的进程内缓存：(mtime, size, payload)
_CACHE: dict[str, tuple[float, int, dict]] = {}


def _error(code: str, status: int, detail=None) -> JSONResponse:
    body = {
        "code": code,
        "message": ERROR_MESSAGES.get(code, {"zh": "请求失败", "en": "Request failed"}),
    }
    if detail is not None:
        body["detail"] = detail
    return JSONResponse(status_code=status, content=body)


def _permission(user: dict | None) -> int:
    return int((user or {}).get("permission") or 0)


def _author(user: dict) -> dict:
    return {
        "uid": int(user.get("uid") or 0),
        "name": user.get("fullname") or user.get("username") or str(user.get("uid") or ""),
    }


def _with_effective_y(data: dict) -> dict:
    """给车站补上「实际生效的 y」与来源：explicit（手填）/ picked（取点）/ default。"""
    start_y = read_config().get("map", {}).get("start_y", 80)
    stations = []
    for station in data.get("stations") or []:
        item = dict(station)
        if "y" in item:
            item["y_source"] = item.get("y_source") or "explicit"
        else:
            item["y"] = start_y
            item["y_source"] = "default"
        stations.append(item)
    out = dict(data)
    out["stations"] = stations
    return out


def _current_payload() -> dict:
    """读当前版本（带 (mtime, size) 缓存）；读不出来返回 available=False。"""
    try:
        stat = TRANSIT_PATH.stat()
    except OSError:
        return {"available": False, "error": "transit.yml 不存在"}

    cached = _CACHE.get("payload")
    if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
        return cached[2]

    try:
        data, version, warnings = load_current()
        store = read_store()
        current = (store.get("versions") or [{}])[-1]
    except TransitConfigError as exc:
        print(f"[transit] 数据不可用：{exc}", flush=True)
        return {"available": False, "error": str(exc)}

    for message in warnings:
        print(f"[transit] 告警：{message}", flush=True)

    payload = {
        "available": True,
        "version": version,
        "updated_at": current.get("created_at"),
        "summary": current.get("summary") or "",
        "stats": {"lines": len(data.get("lines") or []), "stations": len(data.get("stations") or [])},
        "warnings": warnings,
        "data": _with_effective_y(data),
    }
    _CACHE["payload"] = (stat.st_mtime, stat.st_size, payload)
    return payload


@router.get("/api/map/transit")
def transit_current(authorization: str = Header(None)):
    """当前版本（公开）。"""
    user = get_current_user(authorization)
    payload = dict(_current_payload())
    payload["can_edit"] = _permission(user) >= _EDIT_PERMISSION
    payload["can_force"] = _permission(user) >= _FORCE_PERMISSION
    return payload


@router.get("/api/map/transit/versions")
def transit_versions():
    """历史版本列表（公开，不含 data）。"""
    try:
        store = read_store()
    except TransitConfigError as exc:
        return {"available": False, "error": str(exc), "versions": []}
    versions = []
    for doc in store.get("versions") or []:
        data = doc.get("data") or {}
        versions.append({
            "id": doc.get("id"),
            "parent": doc.get("parent"),
            "created_at": doc.get("created_at"),
            "author": doc.get("author") or {},
            "summary": doc.get("summary") or "",
            "stats": {
                "lines": len(data.get("lines") or []),
                "stations": len(data.get("stations") or []),
            },
        })
    versions.reverse()  # 最新在前
    return {"available": True, "current": versions[0]["id"] if versions else None, "versions": versions}


@router.get("/api/map/transit/versions/{version_id}")
def transit_version(version_id: str, authorization: str = Header(None)):
    """单个版本内容（≥3）：回退预览 / 版本对比用。"""
    user = get_current_user(authorization)
    if user is None:
        return _error("unauthorized", 401)
    if _permission(user) < _EDIT_PERMISSION:
        return _error("permission_denied", 403)
    try:
        store = read_store()
    except TransitConfigError as exc:
        return _error("transit_unavailable", 503, str(exc))
    doc = next((item for item in store.get("versions") or [] if str(item.get("id")) == version_id), None)
    if doc is None:
        return _error("transit_version_not_found", 404, version_id)
    return {
        "id": doc.get("id"),
        "parent": doc.get("parent"),
        "created_at": doc.get("created_at"),
        "author": doc.get("author") or {},
        "summary": doc.get("summary") or "",
        "data": _with_effective_y(validate_data(doc.get("data"))[0]),
    }


@router.get("/api/map/transit/diff")
def transit_diff(from_version: str, to_version: str, authorization: str = Header(None)):
    """两个版本的结构化差异（≥3）。"""
    user = get_current_user(authorization)
    if user is None:
        return _error("unauthorized", 401)
    if _permission(user) < _EDIT_PERMISSION:
        return _error("permission_denied", 403)
    try:
        store = read_store()
    except TransitConfigError as exc:
        return _error("transit_unavailable", 503, str(exc))
    docs = {str(item.get("id")): item for item in store.get("versions") or []}
    if from_version not in docs or to_version not in docs:
        return _error("transit_version_not_found", 404)
    changes = diff_versions(docs[from_version].get("data") or {}, docs[to_version].get("data") or {})
    return {"from": from_version, "to": to_version, "changes": changes}


@router.post("/api/map/transit/validate")
def transit_validate(payload: dict = Body(...), authorization: str = Header(None)):
    """干跑校验，不落盘（≥3）。"""
    user = get_current_user(authorization)
    if user is None:
        return _error("unauthorized", 401)
    if _permission(user) < _EDIT_PERMISSION:
        return _error("permission_denied", 403)
    try:
        _, warnings = validate_data(payload.get("data"), require_lines=True)
    except TransitConfigError as exc:
        return _error("transit_invalid", 400, str(exc))
    return {"ok": True, "warnings": warnings}


@router.post("/api/map/transit")
def transit_submit(payload: dict = Body(...), authorization: str = Header(None)):
    """提交新版本（≥3；冲突 409；force 强制并入仅 ≥4）。"""
    user = get_current_user(authorization)
    if user is None:
        return _error("unauthorized", 401)
    if _permission(user) < _EDIT_PERMISSION:
        return _error("permission_denied", 403)

    force = bool(payload.get("force"))
    if force and _permission(user) < _FORCE_PERMISSION:
        return _error("transit_force_forbidden", 403)

    try:
        result = submit(
            payload.get("data"),
            base_version=payload.get("base_version"),
            author=_author(user),
            summary=str(payload.get("summary") or ""),
            force=force,
        )
    except TransitConfigError as exc:
        return _error("transit_invalid", 400, str(exc))
    except TransitConflictError as exc:
        return _error("transit_conflict", 409, {
            "base_version": exc.base_version,
            "current_version": exc.current_version,
            "conflicts": exc.conflicts,
        })
    except OSError as exc:
        print(f"[transit] 写入失败：{exc}", flush=True)
        return _error("transit_unavailable", 503, str(exc))

    _CACHE.pop("payload", None)
    return JSONResponse(status_code=201, content={
        "ok": True,
        "created": result.get("created"),
        "version": result.get("version"),
        "summary": result.get("summary"),
        "warnings": result.get("warnings") or [],
        "compacted": result.get("compacted", False),
    })


@router.post("/api/map/transit/rollback")
def transit_rollback(payload: dict = Body(...), authorization: str = Header(None)):
    """回退到指定版本（≥3）；生成新版本，历史保留。"""
    user = get_current_user(authorization)
    if user is None:
        return _error("unauthorized", 401)
    if _permission(user) < _EDIT_PERMISSION:
        return _error("permission_denied", 403)

    target = str(payload.get("version_id") or "")
    if not target:
        return _error("transit_invalid", 400, "version_id 不能为空")
    try:
        result = rollback(target, author=_author(user), summary=payload.get("summary"))
    except TransitConfigError as exc:
        return _error("transit_version_not_found", 404, str(exc))
    except OSError as exc:
        print(f"[transit] 回退写入失败：{exc}", flush=True)
        return _error("transit_unavailable", 503, str(exc))

    _CACHE.pop("payload", None)
    return JSONResponse(status_code=201, content={
        "ok": True,
        "created": result.get("created"),
        "version": result.get("version"),
        "summary": result.get("summary"),
    })
