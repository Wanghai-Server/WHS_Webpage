"""头像上传 / 读取路由。"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse

from data.main.database.user_database import UserNotFoundError

from main import (
    AVATAR_DIR,
    AVATAR_CONTENT_TYPES,
    MAX_AVATAR_SIZE,
    _error_response,
    get_current_user,
    user_db,
)

router = APIRouter()


@router.post("/api/user/{uid}/avatar")
async def upload_avatar(uid: int, file: UploadFile = File(...), user: dict | None = Depends(get_current_user)):
    """上传头像：校验类型/大小，落盘并更新 users.avatar（需本人或管理员）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if user["uid"] != uid and (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
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


@router.get("/api/user/{uid}/avatar")
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
