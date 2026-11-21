"""媒体上传共享工具。

Wiki 媒体上传与全站 Markdown 编辑器的文件上传共用同一套白名单、大小限制与
落盘 / 读取逻辑，避免两处规则漂移：

- 图片：png / jpg / jpeg / webp / gif，上限 5MB；
- 视频：mp4 / webm / mov，上限 50MB；
- 音频：mp3 / wav / ogg / m4a / aac / flac，上限 20MB。
"""
import mimetypes
import re
import uuid
from pathlib import Path

from fastapi.responses import FileResponse

from main import _error_response

IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif"}
VIDEO_EXTS = {"mp4", "webm", "mov"}
AUDIO_EXTS = {"mp3", "wav", "ogg", "m4a", "aac", "flac"}
ALLOWED_EXTS = IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS

# 各类型大小上限（字节）：图片 5MB / 视频 50MB / 音频 20MB
MAX_IMAGE_SIZE = 5 * 1024 * 1024
MAX_VIDEO_SIZE = 50 * 1024 * 1024
MAX_AUDIO_SIZE = 20 * 1024 * 1024

# 已保存文件名（uuid hex + 扩展名）校验，防路径穿越
UPLOAD_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,119}$")


def media_type(ext: str) -> str:
    """扩展名 -> 媒体类型（image / video / audio）。"""
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return "audio"


def size_limit(ext: str) -> int:
    """扩展名 -> 大小上限（字节）。"""
    if ext in IMAGE_EXTS:
        return MAX_IMAGE_SIZE
    if ext in VIDEO_EXTS:
        return MAX_VIDEO_SIZE
    return MAX_AUDIO_SIZE


def file_ext(filename: str) -> str:
    """取上传文件名的扩展名（小写；去掉目录部分）。"""
    original = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    return (original.rsplit(".", 1)[-1] if "." in original else "").lower()


def original_name(filename: str) -> str:
    """取上传文件名去掉目录后的原始名称（用于回显）。"""
    return (filename or "").replace("\\", "/").rsplit("/", 1)[-1]


async def read_upload(upload, limit: int):
    """流式读取上传内容并限制大小。

    返回 ``bytes``；超过 ``limit`` 时返回 ``None``（由调用方转成 413）。
    """
    data = bytearray()
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > limit:
            return None
    return bytes(data)


def save_upload(directory: Path, data: bytes, ext: str) -> str:
    """随机文件名保存上传内容，返回落盘文件名。"""
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    (directory / name).write_bytes(data)
    return name


def serve_upload(directory: Path, filename: str, not_found_code: str):
    """读取已上传文件（公开）；非法文件名 / 文件不存在时返回结构化 404。"""
    if UPLOAD_NAME_RE.fullmatch(filename or "") is None:
        return _error_response(not_found_code, 404)
    path = directory / filename
    if not path.is_file():
        return _error_response(not_found_code, 404)
    media = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media)
