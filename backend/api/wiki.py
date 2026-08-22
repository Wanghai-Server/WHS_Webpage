"""维基路由：页面 CRUD / 修订时间线 / 搜索 / 媒体上传。

全部挂载在 /api/wiki 前缀下。读取公开；页面写入按该页的最小编辑权限校验，
媒体上传要求 permission >= 2（与常规页面编辑一致）。

双语机制：内容接口接受 ``lang=zh|en`` 查询参数，前端切换语言时向后端
请求对应语言的内容；界面文案由 vue-i18n 提供。

数据层抛出的 :class:`WikiDatabaseError`（如 slug 冲突、乐观锁冲突、子页删除）
由 main.py 注册的全局异常处理器统一翻译为结构化 + 双语错误响应。
"""
import mimetypes
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, UploadFile
from fastapi.responses import FileResponse

from data.main.database.wiki_database import (
    DEFAULT_MIN_PERMISSION,
    LANGS,
    MAX_CONTENT_LENGTH,
    MAX_SUMMARY_LENGTH,
    WikiLangInvalidError,
    WikiPermissionInvalidError,
    validate_min_permission,
)
from main import _error_response, get_current_user, user_db, wiki_db

router = APIRouter()

# 可调整页面最小编辑权限的最低权限（admin/owner；可把页面权限设为 2/3/4）。
PERMISSION_ADMIN = 3

# ---------------------------------------------------------------------------
# 媒体上传：文件保存到 data/wiki_upload/（已加入 .gitignore）
# ---------------------------------------------------------------------------
WIKI_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "wiki_upload"

IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif"}
VIDEO_EXTS = {"mp4", "webm", "mov"}
AUDIO_EXTS = {"mp3", "wav", "ogg", "m4a", "aac", "flac"}
ALLOWED_EXTS = IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS

# 各类型大小上限（字节）：图片 5MB / 视频 50MB / 音频 20MB
MAX_UPLOAD_SIZE = 5 * 1024 * 1024
_UPLOAD_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,119}$")


def _normalize_lang(lang: str) -> str:
    """规范化语言参数；非法时抛出 :class:`WikiLangInvalidError`。"""
    lang = (lang or "zh").strip().lower()
    if lang not in LANGS:
        raise WikiLangInvalidError(f"不支持的语言：{lang!r}")
    return lang


def _is_wiki_writer(user: dict | None, min_permission: int = DEFAULT_MIN_PERMISSION) -> bool:
    """判断用户是否达到指定页面的最小编辑权限。"""
    return user is not None and (user.get("permission") or 0) >= min_permission


def _require_wiki_writer(user: dict | None, min_permission: int = DEFAULT_MIN_PERMISSION):
    """写入权限检查：未登录 / 权限不足时返回错误响应，否则返回 None。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if not _is_wiki_writer(user, min_permission):
        return _error_response("permission_denied", 403)
    return None


def _require_page_writer(user: dict | None, page: dict):
    """按页面的 min_permission 检查写入权限。"""
    return _require_wiki_writer(
        user, page.get("min_permission") or DEFAULT_MIN_PERMISSION
    )


def _attach_wiki_authors(item: dict) -> dict:
    """把 author_uid / updated_by_uid 解析为作者名称，写入条目。

    条目缺少作者字段时（如部分列表接口）静默跳过。
    """
    author_uid = item.get("author_uid")
    updater_uid = item.get("updated_by_uid")
    author = user_db.get_user(uid=author_uid) if author_uid is not None else None
    updater = user_db.get_user(uid=updater_uid) if updater_uid is not None else None
    item["author_name"] = (
        (author.get("fullname") or author.get("username") or "") if author else ""
    )
    item["updated_by_name"] = (
        (updater.get("fullname") or updater.get("username") or "") if updater else ""
    )
    return item


def _available_langs(page: dict) -> list[str]:
    """页面已编写内容的语言列表。"""
    return [lang for lang in LANGS if (page.get(f"content_{lang}") or "").strip()]


def _page_view(page: dict, lang: str) -> dict:
    """把 pages 行转换为按语言取值的对外结构。"""
    lang = _normalize_lang(lang)
    return {
        "id": page["id"],
        "slug": page["slug"],
        "lang": lang,
        "title": page.get(f"title_{lang}") or "",
        "content": page.get(f"content_{lang}") or "",
        "available_langs": _available_langs(page),
        "min_permission": page.get("min_permission") or DEFAULT_MIN_PERMISSION,
        "disambig": bool(page.get("disambig")),
        "rev_no": wiki_db._current_rev_no(page["id"], lang),
        "author_uid": page["author_uid"],
        "updated_by_uid": page["updated_by_uid"],
        "created_at": page["created_at"],
        "updated_at": page["updated_at"],
    }


# ---------------------------------------------------------------------------
# 页面清单 / 搜索（公开）
# ---------------------------------------------------------------------------


@router.get("/api/wiki/pages")
def wiki_pages():
    """全部页面的列表元信息（不含正文，含双语标题与语言可用性），供首页与侧栏使用。"""
    pages = wiki_db.list_pages()
    for page in pages:
        _attach_wiki_authors(page)
    return {"pages": pages}


@router.get("/api/wiki/search")
def wiki_search(q: str = "", lang: str = "zh"):
    """对指定语言的标题 + 正文做 LIKE 搜索，返回带命中片段的页面列表。"""
    lang = _normalize_lang(lang)
    query = (q or "").strip()[:100]
    results = wiki_db.search_pages(query, lang=lang)
    for item in results:
        _attach_wiki_authors(item)
    return {"query": query, "lang": lang, "results": results}


# ---------------------------------------------------------------------------
# 修订（读取公开；恢复需写入权限）
# ---------------------------------------------------------------------------
# 注意注册顺序：/api/wiki/page/{slug:path}/history 必须先于
# /api/wiki/page/{slug:path} 注册，否则 Starlette 会把 ".../history"
# 当作 slug 的一部分被通用路由吞掉。


@router.get("/api/wiki/page/{slug:path}/history")
def wiki_page_history(slug: str, lang: str = "zh"):
    """页面指定语言的修订时间线（最新在前）。"""
    lang = _normalize_lang(lang)
    page = wiki_db.get_page(slug)
    if page is None:
        return _error_response("wiki_page_not_found", 404)
    revisions = wiki_db.list_revisions(page["id"], lang=lang)
    for revision in revisions:
        author = user_db.get_user(uid=revision.get("author_uid"))
        revision["author_name"] = (
            (author.get("fullname") or author.get("username") or "") if author else ""
        )
    return {"page": _page_view(page, lang), "revisions": revisions}


@router.get("/api/wiki/revision/{rev_id}")
def wiki_revision(rev_id: int):
    """读取单条修订的完整快照（title + content + lang）。"""
    revision = wiki_db.get_revision(rev_id)
    if revision is None:
        return _error_response("wiki_revision_not_found", 404)
    author = user_db.get_user(uid=revision.get("author_uid"))
    revision["author_name"] = (
        (author.get("fullname") or author.get("username") or "") if author else ""
    )
    return {"revision": revision}


@router.post("/api/wiki/revision/{rev_id}/restore")
def wiki_restore(rev_id: int, user: dict | None = Depends(get_current_user)):
    """把指定修订恢复为该页面对应语言的新修订（按页面的最小编辑权限校验）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    revision = wiki_db.get_revision(rev_id)
    if revision is None:
        return _error_response("wiki_revision_not_found", 404)
    page_row = wiki_db.get_page_by_id(revision["page_id"])
    if page_row is None:
        return _error_response("wiki_page_not_found", 404)
    denied = _require_page_writer(user, page_row)
    if denied is not None:
        return denied
    page = wiki_db.restore_revision(revision["page_id"], rev_id, user["uid"])
    return {"success": True, "page": _page_view(page, revision["lang"])}


# ---------------------------------------------------------------------------
# 页面（读取公开；写入按页面 min_permission 校验；调整权限仅管理员）
# ---------------------------------------------------------------------------


@router.put("/api/wiki/page/{slug:path}/permission")
def wiki_set_permission(
    slug: str,
    payload: dict = Body(...),
    user: dict | None = Depends(get_current_user),
):
    """调整页面的最小编辑权限（2/3/4）；仅管理员（permission >= 3）。

    与用户权限管理（admin）规则一致：
    - 不能操作更高编辑权限等级的页面（cannot_modify_higher_permission）；
    - 不能把页面权限设置得高于自己的权限（new_permission_higher）。
    """
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < PERMISSION_ADMIN:
        return _error_response("permission_denied", 403)
    page_row = wiki_db.get_page(slug)
    if page_row is None:
        return _error_response("wiki_page_not_found", 404)
    # 不能操作更高编辑权限等级的页面（与 admin 的 canSetPermission 一致）
    if (user.get("permission") or 0) < (page_row.get("min_permission") or DEFAULT_MIN_PERMISSION):
        return _error_response("cannot_modify_higher_permission", 403)
    try:
        value = validate_min_permission(payload.get("min_permission"))
    except WikiPermissionInvalidError:
        return _error_response("wiki_permission_invalid", 400)
    # 不能把页面权限设置得高于自己的权限（与 admin 的 new_permission_higher 一致）
    if value > (user.get("permission") or 0):
        return _error_response("new_permission_higher", 400)
    page = wiki_db.set_min_permission(slug, value)
    return {"success": True, "min_permission": value, "page": _page_view(page, "zh")}


@router.get("/api/wiki/page/{slug:path}")
def wiki_page(slug: str, lang: str = "zh"):
    """读取页面指定语言的 Markdown 原文、元信息与历史贡献者。

    页面不存在时检查重定向：命中则返回 {"page": null, "redirect": "<目标路径>"}，
    由前端路由替换跳转（旧链接自动跟随改名）。
    """
    lang = _normalize_lang(lang)
    page = wiki_db.get_page(slug)
    if page is None:
        target = wiki_db.resolve_redirect(slug)
        if target is not None:
            return {"page": None, "redirect": target}
        return _error_response("wiki_page_not_found", 404)
    view = _page_view(page, lang)
    view["revisions_count"] = len(wiki_db.list_revisions(page["id"], lang=lang))
    _attach_wiki_authors(view)
    # 历史贡献者：谁编写过该页面（uid 0 为系统播种，名称留空由前端显示"系统"）
    contributors = []
    for item in wiki_db.list_contributors(page["id"]):
        author = user_db.get_user(uid=item["author_uid"]) if item["author_uid"] else None
        item["name"] = (
            (author.get("fullname") or author.get("username") or "") if author else ""
        )
        contributors.append(item)
    view["contributors"] = contributors
    return {"page": view}


@router.post("/api/wiki/page")
def wiki_create(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """创建页面：{slug, content, lang, min_permission?, disambig?}。

    标题自动从对应语言 Markdown 的第一个 H1 提取。
    最小编辑权限默认 2；仅管理员（permission >= 3）可在创建时指定 2/3/4。
    """
    if user is None:
        return _error_response("unauthorized", 401)
    slug = payload.get("slug")
    content = payload.get("content")
    try:
        lang = _normalize_lang(payload.get("lang"))
    except WikiLangInvalidError:
        return _error_response("wiki_lang_invalid", 400)
    # 最小编辑权限：管理员可在创建时指定，普通成员固定为默认 2
    min_permission = DEFAULT_MIN_PERMISSION
    if (user.get("permission") or 0) >= PERMISSION_ADMIN:
        raw = payload.get("min_permission")
        if raw is not None:
            try:
                min_permission = validate_min_permission(raw)
            except WikiPermissionInvalidError:
                return _error_response("wiki_permission_invalid", 400)
    denied = _require_wiki_writer(user, min_permission)
    if denied is not None:
        return denied
    if not isinstance(slug, str) or not slug.strip():
        return _error_response("wiki_slug_invalid", 400)
    if not isinstance(content, str) or not content.strip():
        return _error_response("wiki_content_empty", 400)
    if len(content) > MAX_CONTENT_LENGTH:
        return _error_response("wiki_content_too_large", 413)
    page = wiki_db.create_page(
        slug.strip(), content, user["uid"], lang=lang, min_permission=min_permission,
        disambig=bool(payload.get("disambig")),
    )
    return {"success": True, "page": _page_view(page, lang)}


@router.put("/api/wiki/page/{slug:path}")
def wiki_update(
    slug: str,
    payload: dict = Body(...),
    user: dict | None = Depends(get_current_user),
):
    """更新页面指定语言：{content, lang, base_rev, summary?, disambig?}。乐观锁冲突返回 409。"""
    if user is None:
        return _error_response("unauthorized", 401)
    page_row = wiki_db.get_page(slug)
    if page_row is None:
        return _error_response("wiki_page_not_found", 404)
    denied = _require_page_writer(user, page_row)
    if denied is not None:
        return denied
    content = payload.get("content")
    try:
        lang = _normalize_lang(payload.get("lang"))
    except WikiLangInvalidError:
        return _error_response("wiki_lang_invalid", 400)
    base_rev = payload.get("base_rev")
    summary = payload.get("summary")
    disambig = payload.get("disambig")
    if not isinstance(content, str) or not content.strip():
        return _error_response("wiki_content_empty", 400)
    if len(content) > MAX_CONTENT_LENGTH:
        return _error_response("wiki_content_too_large", 413)
    if summary is not None:
        summary = str(summary).strip()[:MAX_SUMMARY_LENGTH] or None
    if base_rev is not None:
        try:
            base_rev = int(base_rev)
        except (TypeError, ValueError):
            base_rev = None
    page = wiki_db.update_page(
        slug, content, user["uid"], lang=lang, base_rev=base_rev, summary=summary,
        disambig=None if disambig is None else bool(disambig),
    )
    return {"success": True, "page": _page_view(page, lang)}


@router.delete("/api/wiki/page/{slug:path}")
def wiki_delete(slug: str, user: dict | None = Depends(get_current_user)):
    """删除页面及其全部修订（按页面最小编辑权限校验）；存在子页面时返回 409。"""
    if user is None:
        return _error_response("unauthorized", 401)
    page_row = wiki_db.get_page(slug)
    if page_row is None:
        return _error_response("wiki_page_not_found", 404)
    denied = _require_page_writer(user, page_row)
    if denied is not None:
        return denied
    wiki_db.delete_page(slug)
    return {"success": True}


# ---------------------------------------------------------------------------
# 重定向管理（页面改名后旧路径自动跳转；管理操作仅管理员 >= 3）
# ---------------------------------------------------------------------------


@router.get("/api/wiki/redirects")
def wiki_redirects(user: dict | None = Depends(get_current_user)):
    """重定向列表（仅管理员）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < PERMISSION_ADMIN:
        return _error_response("permission_denied", 403)
    return {"redirects": wiki_db.list_redirects()}


@router.post("/api/wiki/redirects")
def wiki_create_redirect(
    payload: dict = Body(...),
    user: dict | None = Depends(get_current_user),
):
    """创建（或覆盖）一条重定向：{from_slug, to_slug}（仅管理员）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < PERMISSION_ADMIN:
        return _error_response("permission_denied", 403)
    from_slug = payload.get("from_slug")
    to_slug = payload.get("to_slug")
    if not isinstance(from_slug, str) or not from_slug.strip():
        return _error_response("wiki_slug_invalid", 400)
    if not isinstance(to_slug, str) or not to_slug.strip():
        return _error_response("wiki_slug_invalid", 400)
    item = wiki_db.create_redirect(from_slug.strip(), to_slug.strip())
    return {"success": True, "redirect": item}


@router.delete("/api/wiki/redirects/{from_slug:path}")
def wiki_delete_redirect(from_slug: str, user: dict | None = Depends(get_current_user)):
    """删除一条重定向（仅管理员）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < PERMISSION_ADMIN:
        return _error_response("permission_denied", 403)
    if not wiki_db.delete_redirect(from_slug):
        return _error_response("wiki_redirect_not_found", 404)
    return {"success": True}


# ---------------------------------------------------------------------------
# 系统消歧义页（自动构建）
# ---------------------------------------------------------------------------


@router.post("/api/wiki/disambig/rebuild")
def wiki_rebuild_disambig(user: dict | None = Depends(get_current_user)):
    """手动触发系统消歧义页重建（仅管理员；页面写操作也会自动触发）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < PERMISSION_ADMIN:
        return _error_response("permission_denied", 403)
    stats = wiki_db.rebuild_auto_disambig()
    return {"success": True, **stats}


# ---------------------------------------------------------------------------
# 媒体上传（编辑时插入图片 / 视频 / 音频）
# ---------------------------------------------------------------------------


def _upload_media_type(ext: str) -> str:
    """扩展名 -> 媒体类型（image / video / audio）。"""
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return "audio"


@router.post("/api/wiki/upload")
async def wiki_upload(
    file: UploadFile = File(...),
    user: dict | None = Depends(get_current_user),
):
    """上传维基媒体文件（图片 / 视频 / 音频），返回可直接写入 Markdown 的 URL。

    - 仅接受白名单扩展名；大小上限：图片 5MB / 视频 50MB / 音频 20MB；
    - 文件以随机 UUID 文件名保存到 ``data/wiki_upload/``（已 gitignore），
      避免路径穿越与同名覆盖。
    """
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 2:
        return _error_response("permission_denied", 403)
    original = (file.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    ext = (original.rsplit(".", 1)[-1] if "." in original else "").lower()
    if ext not in ALLOWED_EXTS:
        return _error_response("wiki_upload_unsupported", 400)
    # 流式读取并限制大小（1MB 分块）
    limit = MAX_UPLOAD_SIZE if ext in IMAGE_EXTS else (
        50 * 1024 * 1024 if ext in VIDEO_EXTS else 20 * 1024 * 1024
    )
    data = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > limit:
            return _error_response("wiki_upload_too_large", 413)
    if not data:
        return _error_response("wiki_upload_unsupported", 400)
    WIKI_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    (WIKI_UPLOAD_DIR / name).write_bytes(bytes(data))
    return {
        "success": True,
        "url": f"/api/wiki/upload/{name}",
        "type": _upload_media_type(ext),
        "original": original,
    }


@router.get("/api/wiki/upload/{filename}")
def wiki_upload_file(filename: str):
    """读取已上传的维基媒体文件（公开，供页面渲染播放）。"""
    if _UPLOAD_NAME_RE.fullmatch(filename or "") is None:
        return _error_response("wiki_upload_not_found", 404)
    path = WIKI_UPLOAD_DIR / filename
    if not path.is_file():
        return _error_response("wiki_upload_not_found", 404)
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)
