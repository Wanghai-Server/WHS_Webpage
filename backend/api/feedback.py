"""反馈路由：反馈列表 / 详情 / 提交 / 编辑 / 删除 / 评论 / 状态管理。

- 浏览（列表、详情）公开，无需登录；
- 提交反馈、发表评论需要登录；
- 编辑仅反馈作者本人；删除允许作者本人或管理员（permission >= 3）；
- 修改状态仅管理员（permission >= 3）。
"""

from fastapi import APIRouter, Body, Depends

from main import (
    _error_response,
    feedback_db,
    get_current_user,
    user_db,
)
from data.main.database.feedback_database import MAX_PAGE_SIZE

router = APIRouter()

# 管理员权限阈值（3=admin 4=owner）
_ADMIN_PERMISSION = 3


def _author_name(uid: int) -> str:
    """把 uid 解析为展示名称（昵称优先，其次用户名；找不到返回空串）。"""
    if not uid:
        return ""
    user = user_db.get_user(uid=uid)
    if not user:
        return ""
    return user.get("fullname") or user.get("username") or ""


def _is_admin(user: dict | None) -> bool:
    return bool(user) and (user.get("permission") or 0) >= _ADMIN_PERMISSION


def _attach_feedback_meta(item: dict) -> dict:
    """为反馈字典补充作者名称。"""
    item["author_name"] = _author_name(item.get("author_uid"))
    return item


def _validate_string_fields(payload: dict, *fields: str):
    """校验写接口 payload 中给定字段（存在且非 null 时）必须是字符串。

    原先非字符串字段（如 ``{"title": 123}``）会在数据层 ``.strip()`` 处抛
    ``AttributeError`` → 500；这里统一在入口拦截为 400 结构化错误
    （feedback_invalid_field）。字段缺失 / null 维持原语义，交给数据层给出
    feedback_title_empty / feedback_content_empty 等既有错误码。

    :return: 不通过返回错误响应；通过返回 None。
    """
    for field in fields:
        value = payload.get(field)
        if value is not None and not isinstance(value, str):
            return _error_response("feedback_invalid_field", 400)
    return None


@router.get("/api/feedback")
def feedback_list(
    page: int = 1,
    page_size: int = 10,
    status: str = "",
    category: str = "",
    q: str = "",
):
    """反馈列表（公开）：分页 + 状态/分类筛选 + 关键词搜索。"""
    if page_size > MAX_PAGE_SIZE:
        page_size = MAX_PAGE_SIZE
    data = feedback_db.list_feedbacks(
        page=page,
        page_size=page_size,
        status=(status or "").strip(),
        category=(category or "").strip(),
        q=q,
    )
    for item in data["items"]:
        _attach_feedback_meta(item)
    return data


@router.get("/api/feedback/{feedback_id}")
def feedback_detail(feedback_id: int, user: dict | None = Depends(get_current_user)):
    """反馈详情（公开）：包含评论列表与当前浏览者的操作权限标记。"""
    feedback = feedback_db.get_feedback(feedback_id)
    if feedback is None:
        return _error_response("feedback_not_found", 404)

    comments = feedback_db.list_comments(feedback_id)
    for comment in comments:
        comment["author_name"] = _author_name(comment.get("author_uid"))

    is_author = bool(user) and user["uid"] == feedback["author_uid"]
    return {
        "feedback": _attach_feedback_meta(feedback),
        "comments": comments,
        "viewer": {
            "logged_in": user is not None,
            "can_edit": is_author,
            "can_delete": is_author or _is_admin(user),
            "can_moderate": _is_admin(user),
        },
    }


@router.post("/api/feedback")
def feedback_create(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """提交反馈（需登录）：{title, content, category}。"""
    if user is None:
        return _error_response("unauthorized", 401)
    err = _validate_string_fields(payload, "title", "content", "category")
    if err is not None:
        return err
    feedback_id = feedback_db.create_feedback(
        title=payload.get("title") or "",
        content=payload.get("content") or "",
        category=payload.get("category") or "",
        author_uid=user["uid"],
    )
    return {"success": True, "feedback_id": feedback_id}


@router.put("/api/feedback/{feedback_id}")
def feedback_update(
    feedback_id: int,
    payload: dict = Body(...),
    user: dict | None = Depends(get_current_user),
):
    """编辑反馈（仅作者本人）：{title, content, category}。"""
    if user is None:
        return _error_response("unauthorized", 401)
    feedback = feedback_db.get_feedback(feedback_id)
    if feedback is None:
        return _error_response("feedback_not_found", 404)
    if feedback["author_uid"] != user["uid"]:
        return _error_response("permission_denied", 403)
    err = _validate_string_fields(payload, "title", "content", "category")
    if err is not None:
        return err
    feedback_db.update_feedback(
        feedback_id,
        title=payload.get("title") or "",
        content=payload.get("content") or "",
        category=payload.get("category") or "",
    )
    return {"success": True}


@router.delete("/api/feedback/{feedback_id}")
def feedback_delete(feedback_id: int, user: dict | None = Depends(get_current_user)):
    """删除反馈（作者本人或管理员），评论一并删除。"""
    if user is None:
        return _error_response("unauthorized", 401)
    feedback = feedback_db.get_feedback(feedback_id)
    if feedback is None:
        return _error_response("feedback_not_found", 404)
    if feedback["author_uid"] != user["uid"] and not _is_admin(user):
        return _error_response("permission_denied", 403)
    feedback_db.delete_feedback(feedback_id)
    return {"success": True}


@router.post("/api/feedback/{feedback_id}/comments")
def feedback_add_comment(
    feedback_id: int,
    payload: dict = Body(...),
    user: dict | None = Depends(get_current_user),
):
    """发表评论（需登录）：{content}。"""
    if user is None:
        return _error_response("unauthorized", 401)
    err = _validate_string_fields(payload, "content")
    if err is not None:
        return err
    comment_id = feedback_db.add_comment(
        feedback_id, user["uid"], payload.get("content") or ""
    )
    comment = feedback_db.get_comment(comment_id) or {}
    comment["author_name"] = _author_name(user["uid"])
    return {"success": True, "comment": comment}


@router.put("/api/admin/feedback/{feedback_id}/status")
def feedback_set_status(
    feedback_id: int,
    payload: dict = Body(...),
    user: dict | None = Depends(get_current_user),
):
    """修改反馈状态（管理员）：{status: pending|resolved|closed}。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if not _is_admin(user):
        return _error_response("permission_denied", 403)
    err = _validate_string_fields(payload, "status")
    if err is not None:
        return err
    status = (payload.get("status") or "").strip()
    feedback_db.set_status(feedback_id, status)
    return {"success": True, "status": status}
