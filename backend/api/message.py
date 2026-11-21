"""消息路由：系统消息 / 定向消息 / 已读状态 / 管理员消息管理。"""
from fastapi import APIRouter, Body, Depends

from main import (
    _attach_message_author,
    _error_response,
    get_current_user,
    message_db,
)

router = APIRouter()

MESSAGE_TITLE_MAX = 100
MESSAGE_CONTENT_MAX = 20000


def _localized_field(value, max_length: int) -> tuple[str, str]:
    """把 ``{zh, en}``（或旧版字符串）解析为 (中文, 英文) 并截断。

    字符串按旧版单语言字段处理（视为中文）；非法类型返回两个空串，
    由调用方统一返回「不能为空」错误。
    """
    if isinstance(value, dict):
        zh, en = value.get("zh"), value.get("en")
    elif isinstance(value, str):
        zh, en = value, ""
    else:
        return "", ""
    if not isinstance(zh, str) or not isinstance(en, str):
        return "", ""
    return zh.strip()[:max_length], en.strip()[:max_length]


def _serialize_message(message: dict | None) -> dict | None:
    """把数据库行中的 title/content + title_en/content_en 组合为双语对象。

    返回的 ``title`` / ``content`` 均为 ``{zh, en}``；缺失语言由前端按站点语言回退。
    """
    if message is None:
        return None
    data = dict(message)
    title_zh = data.pop("title", "") or ""
    content_zh = data.pop("content", "") or ""
    title_en = data.pop("title_en", "") or ""
    content_en = data.pop("content_en", "") or ""
    data["title"] = {"zh": title_zh, "en": title_en}
    data["content"] = {"zh": content_zh, "en": content_en}
    return data


@router.get("/api/message/system")
def system_messages(user: dict | None = Depends(get_current_user)):
    """系统消息列表（所有人可见）；登录时附带每条消息当前用户是否已读。"""
    messages = [_serialize_message(m) for m in message_db.list_system_messages()]
    for m in messages:
        # 不向客户端暴露其他用户的已读 uid 列表
        m.pop("read_uids", None)
        # 附带发布者名称（供消息盒子展示）
        _attach_message_author(m)
        if user is None:
            m["is_read"] = None
        else:
            m["is_read"] = message_db.is_read_by(m["id"], user["uid"])
    return {"messages": messages}


@router.get("/api/message/unread_count")
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


@router.post("/api/message/{message_id}/read")
def mark_message_read(message_id: int, user: dict | None = Depends(get_current_user)):
    """把当前用户标记为该消息已读（幂等）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if message_db.get_message(message_id) is None:
        return _error_response("message_not_found", 404)
    message_db.add_read_user(message_id, user["uid"])
    return {"success": True, "is_read": True}


@router.post("/api/message/read_all")
def mark_all_messages_read(user: dict | None = Depends(get_current_user)):
    """把当前用户可见的全部消息（系统 + 定向）标记为已读（幂等）→「全部已读」。"""
    if user is None:
        return _error_response("unauthorized", 401)
    marked = message_db.mark_all_read(user["uid"])
    return {"success": True, "marked": marked, "unread_count": 0}


@router.post("/api/admin/messages")
def publish_message(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """管理员发布系统消息（双语标题 + Markdown 内容）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    title_zh, title_en = _localized_field(payload.get("title"), MESSAGE_TITLE_MAX)
    content_zh, content_en = _localized_field(payload.get("content"), MESSAGE_CONTENT_MAX)
    if not title_zh and not title_en:
        return _error_response("message_title_empty", 400)
    if not content_zh and not content_en:
        return _error_response("message_content_empty", 400)
    message_id = message_db.create_message(
        title_zh,
        content_zh,
        user["uid"],
        scope="system",
        title_en=title_en,
        content_en=content_en,
    )
    message = message_db.get_message(message_id)
    _attach_message_author(message)
    return {"success": True, "message": _serialize_message(message)}


@router.put("/api/admin/messages/{message_id}")
def edit_message(message_id: int, payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """管理员编辑自己发布的系统消息（双语标题 + Markdown 内容）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    msg = message_db.get_message(message_id)
    if msg is None:
        return _error_response("message_not_found", 404)
    if msg["author_uid"] != user["uid"]:
        return _error_response("permission_denied", 403)
    title_zh, title_en = _localized_field(payload.get("title"), MESSAGE_TITLE_MAX)
    content_zh, content_en = _localized_field(payload.get("content"), MESSAGE_CONTENT_MAX)
    if not title_zh and not title_en:
        return _error_response("message_title_empty", 400)
    if not content_zh and not content_en:
        return _error_response("message_content_empty", 400)
    message_db.update_message(message_id, title_zh, content_zh, title_en, content_en)
    message = message_db.get_message(message_id)
    _attach_message_author(message)
    return {"success": True, "message": _serialize_message(message)}


@router.delete("/api/admin/messages/{message_id}")
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


@router.get("/api/message/{user_id}")
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
    messages = [_serialize_message(m) for m in message_db.list_user_messages(uid)]
    for m in messages:
        m.pop("read_uids", None)
        _attach_message_author(m)
        m["is_read"] = message_db.is_read_by(m["id"], user["uid"])
    return {"messages": messages}
