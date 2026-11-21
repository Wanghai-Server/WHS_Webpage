"""维基路由：页面 CRUD / 修订时间线 / 搜索 / 媒体上传。

全部挂载在 /api/wiki 前缀下。读取公开；页面写入按该页的最小编辑权限校验，
媒体上传要求 permission >= 2（与常规页面编辑一致）。

双语机制：内容接口接受 ``lang=zh|en`` 查询参数，前端切换语言时向后端
请求对应语言的内容；界面文案由 vue-i18n 提供。

数据层抛出的 :class:`WikiDatabaseError`（如 slug 冲突、乐观锁冲突、子页删除）
由 main.py 注册的全局异常处理器统一翻译为结构化 + 双语错误响应。
"""
import io
import re

from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, UploadFile

from api.media_upload import (
    ALLOWED_EXTS,
    IMAGE_EXTS,
    MAX_IMAGE_SIZE,
    file_ext,
    media_type,
    original_name,
    read_upload,
    save_upload,
    serve_upload,
    size_limit,
)
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
#
# 白名单 / 大小限制 / 落盘与读取逻辑与全站 Markdown 编辑器共用
# （api/media_upload.py），仅存储目录与权限要求不同。
# ---------------------------------------------------------------------------


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
    ext = file_ext(file.filename)
    if ext not in ALLOWED_EXTS:
        return _error_response("wiki_upload_unsupported", 400)
    data = await read_upload(file, size_limit(ext))
    if data is None:
        return _error_response("wiki_upload_too_large", 413)
    if not data:
        return _error_response("wiki_upload_unsupported", 400)
    name = save_upload(WIKI_UPLOAD_DIR, data, ext)
    return {
        "success": True,
        "url": f"/api/wiki/upload/{name}",
        "type": media_type(ext),
        "original": original_name(file.filename),
    }


@router.get("/api/wiki/upload/{filename}")
def wiki_upload_file(filename: str):
    """读取已上传的维基媒体文件（公开，供页面渲染播放）。"""
    return serve_upload(WIKI_UPLOAD_DIR, filename, "wiki_upload_not_found")


# ---------------------------------------------------------------------------
# 文档导入（Word / Excel -> Markdown）
#
# 作者上传 .docx / .xlsx，服务端转成 Markdown 正文返回，前端插进编辑器，
# 由作者确认后再保存，避免格式问题直接写进词条。
# 依赖 python-docx / openpyxl，未安装时返回 wiki_import_unavailable。
# ---------------------------------------------------------------------------
IMPORT_EXTS = {"docx", "xlsx"}
IMPORT_MAX_SIZE = 30 * 1024 * 1024
# 表格单元格总数上限，防止超大表把响应撑爆
IMPORT_MAX_CELLS = 20000

_HEADING_RE = re.compile(r"^(?:Heading|标题)\s*([1-6])$", re.IGNORECASE)
_DOCX_BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
_DOCX_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"


def _md_cell(value) -> str:
    """表格单元格转义：竖线、反斜杠和换行都要处理，否则表格会散架。"""
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def _rows_to_md(rows: list[list[str]]) -> str:
    """二维表转 Markdown 表格；首行当表头，空表返回空串。"""
    grid = [[_md_cell(c) for c in row] for row in rows if any(str(c or "").strip() for c in row)]
    if not grid:
        return ""
    width = max(len(r) for r in grid)
    grid = [r + [""] * (width - len(r)) for r in grid]
    head = "| " + " | ".join(grid[0]) + " |"
    sep = "| " + " | ".join(["---"] * width) + " |"
    body = ["| " + " | ".join(r) + " |" for r in grid[1:]]
    return "\n".join([head, sep] + body)


def _save_import_image(blob: bytes, ext: str) -> str:
    """把 Word 里的图片存进维基上传目录，返回可直接写进 Markdown 的地址。"""
    if ext not in IMAGE_EXTS or len(blob) > MAX_IMAGE_SIZE:
        return ""
    name = save_upload(WIKI_UPLOAD_DIR, blob, ext)
    return f"/api/wiki/upload/{name}"


def _docx_runs_md(paragraph, doc) -> str:
    """段落内按 run 拼 Markdown：保留粗体、斜体和图片。"""
    parts = []
    for run in paragraph.runs:
        for blip in run._element.findall(f".//{_DOCX_BLIP}"):
            rid = blip.get(_DOCX_EMBED)
            part = doc.part.related_parts.get(rid) if rid else None
            if part is None:
                continue
            url = _save_import_image(part.blob, (part.partname.ext or "png").lower())
            if url:
                parts.append(f"![]({url})")
        text = run.text
        if not text:
            continue
        core = text.strip()
        if not core:
            parts.append(text)
            continue
        if run.bold and run.italic:
            core = f"***{core}***"
        elif run.bold:
            core = f"**{core}**"
        elif run.italic:
            core = f"*{core}*"
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        parts.append(f"{lead}{core}{trail}")
    return "".join(parts)


def _docx_paragraph_md(paragraph, doc) -> str:
    """单个段落 -> Markdown 块（标题 / 列表 / 引用 / 普通段落）。"""
    style = (paragraph.style.name if paragraph.style is not None else "") or ""
    body = _docx_runs_md(paragraph, doc).strip()
    if not body:
        return ""
    heading = _HEADING_RE.match(style)
    if heading:
        return "#" * int(heading.group(1)) + " " + body
    if style in ("Title", "标题"):
        return "# " + body
    low = style.lower()
    if "list bullet" in low or "列表段落" in style:
        return "- " + body
    if "list number" in low or "列表编号" in style:
        return "1. " + body
    if "quote" in low or "引用" in style:
        return "> " + body
    return body


def _docx_to_markdown(raw: bytes) -> str:
    """Word 正文按原始顺序转 Markdown，表格和内嵌图片一并带过来。"""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(io.BytesIO(raw))
    blocks = []
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            md = _docx_paragraph_md(Paragraph(child, doc), doc)
            if md:
                blocks.append(md)
        elif child.tag.endswith("}tbl"):
            rows = [[cell.text for cell in row.cells] for row in Table(child, doc).rows]
            md = _rows_to_md(rows)
            if md:
                blocks.append(md)
    return "\n\n".join(blocks)


def _xlsx_to_markdown(raw: bytes) -> str:
    """每个工作表转一张 Markdown 表，多表时用二级标题分开。"""
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
    try:
        sections = []
        cells = 0
        for ws in wb.worksheets:
            rows = []
            for row in ws.iter_rows(values_only=True):
                cells += len(row)
                if cells > IMPORT_MAX_CELLS:
                    raise ValueError("too_many_cells")
                values = ["" if v is None else str(v) for v in row]
                if any(v.strip() for v in values):
                    rows.append(values)
            table = _rows_to_md(rows)
            if table:
                sections.append(f"## {ws.title}\n\n{table}")
        return "\n\n".join(sections)
    finally:
        wb.close()


@router.post("/api/wiki/import")
async def wiki_import(
    file: UploadFile = File(...),
    user: dict | None = Depends(get_current_user),
):
    """把 Word / Excel 转成 Markdown 正文（不落库，由前端插入后再保存）。

    - 仅接受 .docx / .xlsx，单文件上限 30MiB；
    - 表格单元格总数超过 20000 时拒绝；
    - Word 内嵌图片会存进 ``data/wiki_upload/``，正文里替换为图片地址。
    """
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 2:
        return _error_response("permission_denied", 403)
    original = original_name(file.filename)
    ext = file_ext(file.filename)
    if ext not in IMPORT_EXTS:
        return _error_response("wiki_import_unsupported", 400)
    data = await read_upload(file, IMPORT_MAX_SIZE)
    if data is None:
        return _error_response("wiki_import_too_large", 413)
    if not data:
        return _error_response("wiki_import_unsupported", 400)
    try:
        markdown = _docx_to_markdown(data) if ext == "docx" else _xlsx_to_markdown(data)
    except ImportError:
        return _error_response("wiki_import_unavailable", 503)
    except ValueError as exc:
        if str(exc) == "too_many_cells":
            return _error_response("wiki_import_too_many_cells", 413)
        return _error_response("wiki_import_failed", 400)
    except Exception:
        # 损坏的压缩包、非 Office 文件等都会在这里被挡住
        return _error_response("wiki_import_failed", 400)
    return {"success": True, "markdown": markdown, "original": original}
