"""全站 Markdown 编辑器上传接口。

- 上传：``POST /api/markdown/upload``（登录用户即可），文件保存到
  ``data/markdown_upload/``（已 gitignore），以随机 UUID 文件名避免覆盖 / 穿越；
- 读取：``GET /api/markdown/upload/{filename}``（公开，供 Markdown 渲染播放）。

文件类型、大小限制与 Wiki 媒体上传完全一致（见 :mod:`api.media_upload`）。
"""
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile

from api.media_upload import (
    ALLOWED_EXTS,
    file_ext,
    media_type,
    original_name,
    read_upload,
    save_upload,
    serve_upload,
    size_limit,
)
from main import _error_response, get_current_user

router = APIRouter()

# 与 Wiki 分开存放：Markdown 编辑器上传的文件进入独立目录
MARKDOWN_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "markdown_upload"


@router.post("/api/markdown/upload")
async def markdown_upload(
    file: UploadFile = File(...),
    user: dict | None = Depends(get_current_user),
):
    """上传 Markdown 编辑器使用的媒体文件，返回可写入 Markdown 的 URL。"""
    if user is None:
        return _error_response("unauthorized", 401)
    ext = file_ext(file.filename)
    if ext not in ALLOWED_EXTS:
        return _error_response("markdown_upload_unsupported", 400)
    data = await read_upload(file, size_limit(ext))
    if data is None:
        return _error_response("markdown_upload_too_large", 413)
    if not data:
        return _error_response("markdown_upload_unsupported", 400)
    name = save_upload(MARKDOWN_UPLOAD_DIR, data, ext)
    return {
        "success": True,
        "url": f"/api/markdown/upload/{name}",
        "type": media_type(ext),
        "original": original_name(file.filename),
    }


@router.get("/api/markdown/upload/{filename}")
def markdown_upload_file(filename: str):
    """读取已上传的 Markdown 媒体文件（公开）。"""
    return serve_upload(MARKDOWN_UPLOAD_DIR, filename, "markdown_upload_not_found")
