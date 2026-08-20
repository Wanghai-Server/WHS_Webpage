"""消息路由：系统消息 / 定向消息 / 已读状态 / 管理员消息管理。"""
from fastapi import APIRouter, Body, Depends

from main import (
    _attach_message_author,
    _error_response,
    get_current_user,
    message_db,
)

router = APIRouter()


@router.get("/api/message/system")
def system_messages(user: dict | None = Depends(get_current_user)):
    """系统消息列表（所有人可见）；登录时附带每条消息当前用户是否已读。"""
    messages = message_db.list_system_messages()
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


@router.post("/api/admin/messages")
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


@router.put("/api/admin/messages/{message_id}")
def edit_message(message_id: int, payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """管理员编辑自己发布的系统消息（标题 + Markdown 内容）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    msg = message_db.get_message(message_id)
    if msg is None:
        return _error_response("message_not_found", 404)
    if msg["author_uid"] != user["uid"]:
        return _error_response("permission_denied", 403)
    title = payload.get("title") or ""
    content = payload.get("content") or ""
    if not isinstance(title, str) or not title.strip():
        return _error_response("message_title_empty", 400)
    if not isinstance(content, str) or not content.strip():
        return _error_response("message_content_empty", 400)
    title = title.strip()[:100]
    content = content.strip()[:20000]
    message_db.update_message(message_id, title, content)
    return {"success": True, "message": message_db.get_message(message_id)}


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
    messages = message_db.list_user_messages(uid)
    for m in messages:
        m.pop("read_uids", None)
        _attach_message_author(m)
        m["is_read"] = message_db.is_read_by(m["id"], user["uid"])
    return {"messages": messages}
