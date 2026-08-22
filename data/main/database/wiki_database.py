"""维基数据库（基于 sqlite3）。

数据库文件由 :class:`BasicDatabase` 统一规范化到 ``data/database/wiki.db``，
内部两张表：

- ``pages``：当前版本的页面（``slug`` 唯一）。页面支持中英双语：
  ``content_zh`` / ``content_en`` 分别存放两种语言的 Markdown 原文，
  ``title_zh`` / ``title_en`` 在保存时自动从对应语言的第一个 H1 提取；
- ``revisions``：每次保存的历史快照（``page_id`` + ``lang`` + ``rev_no``），
  供修订时间线展示与一键回滚，同时记录"谁编写过该页面"（``author_uid``）。

语言切换由前端在切换时向后端发送对应语言的请求（``lang`` 参数）完成，
本模块所有读写接口均以语言为维度。继承 :class:`UserDatabase` 复用其表管理 /
迁移 / 连接生命周期逻辑。

slug 规则：由小写 ASCII 段组成、``/`` 分隔层级（如 ``guide/quick-start``）。
并发安全：更新接口采用乐观锁（``base_rev`` 与当前语言的修订号不符即冲突）。
"""

import datetime
import hashlib
import re
import sqlite3
from collections import defaultdict
from typing import Any

from .user_database import UserDatabase

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 支持的语言。
LANGS = ("zh", "en")

# 每页最小编辑权限的合法取值（2=player 3=admin 4=owner；常规页面默认 2）。
MIN_PERMISSIONS = (2, 3, 4)
DEFAULT_MIN_PERMISSION = 2

# slug 合法规则：小写字母 / 数字 / 短横线组成的分段，以 / 分隔层级。
SLUG_PATTERN = re.compile(r"^[a-z0-9-]+(?:\/[a-z0-9-]+)*$")
SLUG_MAX_LENGTH = 200

# 单语言 Markdown 上限（字符数）。
MAX_CONTENT_LENGTH = 200_000
# 自动提取的标题长度上限。
MAX_TITLE_LENGTH = 200
# 编辑摘要长度上限。
MAX_SUMMARY_LENGTH = 200
# 每页每语言保留的最新修订条数，超出后修剪最旧的。
MAX_REVISIONS = 100

# 播种页：首次启动时若 pages 为空，自动写入欢迎页（双语）。
WELCOME_SLUG = "welcome"
WELCOME_CONTENT_ZH = r"""# 欢迎来到望海服务器维基

这里是望海服务器（WangHai Server）的官方维基，由社区成员共同维护。
所有页面均使用 Markdown 书写，页面目录自动从标题解析，支持中英双语。

## 浏览与搜索

- 顶部**搜索框**：输入关键词即时检索标题与正文；
- 首页**知识分组**：按页面路径（slug）自动归类，快速浏览全部页面；
- 右侧**大纲**：自动跟随阅读进度高亮，点击标题即可跳转；
- 底部**语言切换**：中英双语实时切换，无需刷新页面。

## 编辑与权限

- 通过入服考试的正式成员（权限 2）即可**新建与编辑**常规页面；
- 每次保存都会生成一条**修订记录**，可在历史中查看任意版本并一键回滚；
- 页面底部会展示**贡献者**——谁编写过、各编辑了几次；
- 管理员可将个别页面（如规则、公告）的编辑权限调整为仅管理员（3）或仅服主（4）。

## 新建页面

点击首页的"新建页面"，输入页面路径（slug）后即可书写：

- 路径由小写字母、数字、短横线组成，用 `/` 分层，例如 `guide/quick-start`；
- 合理的路径层级会让页面在首页"知识分组"中自动归类。

## Markdown 语法速览

页面的**第一个一级标题（`#`）作为页面标题**，`##` 及以下的标题自动进入右侧大纲。

| 语法 | 效果 |
| --- | --- |
| `#` `##` `###` … `######` | H1-H6 各级标题：首个 H1 为页面标题，H2+ 进入大纲 |
| `**加粗**`、`*斜体*`、`~~删除线~~` | **加粗**、*斜体*、~~删除线~~ |
| `` `行内代码` `` | `行内代码` |
| 三个反引号包裹 | 代码块（可标注语言） |
| `[文字](https://example.com)` | [文字](https://example.com) |
| `![图片描述](图片地址)` | 插入图片 |
| `> 引用` | 引用块 |
| `- 条目` / `1. 条目` | 无序列表 / 有序列表 |
| `- [ ] 待办` | 任务清单 |
| \| 列1 \| 列2 \| | 表格 |
| `---` | 分割线 |

> 提示：编辑器上方提供完整的语法工具条（H 下拉可选 H1-H6），选中文本后点击即可快速插入。

*—— 望海服务器维基*
"""

WELCOME_CONTENT_EN = r"""# Welcome to the WangHai Server Wiki

This is the official wiki of WangHai Server (WHS), maintained together by the community.
Every page is written in Markdown, with the outline parsed automatically from headings, and both Chinese and English are supported.

## Browse & search

- The **search box** at the top finds pages by keyword in titles and content;
- The **sections** on the home page group pages by their path (slug) for quick browsing;
- The **outline** on the right follows your reading progress; click any heading to jump to it;
- Switch languages from the **footer** — the wiki updates instantly, no reload needed.

## Editing & permissions

- Official members (permission 2) can **create and edit** regular pages;
- Every save creates a **revision** — review any version in the History page and restore it with one click;
- The page footer shows its **contributors** — who wrote it and how many times;
- Admins can raise the edit permission of specific pages (rules, announcements) to Admins (3) or Owner (4).

## Creating a page

Click "New page" on the home page, enter a page path (slug) and start writing:

- Paths use lowercase letters, digits and hyphens, separated by `/`, e.g. `guide/quick-start`;
- A sensible path hierarchy puts the page into the right section on the home page automatically.

## Markdown cheat sheet

The **first H1 (`#`) becomes the page title**; `##` and below go into the outline.

| Syntax | Result |
| --- | --- |
| `#` `##` `###` … `######` | Headings H1-H6: the first H1 is the page title, H2+ enter the outline |
| `**bold**`, `*italic*`, `~~strike~~` | **bold**, *italic*, ~~strike~~ |
| `` `inline code` `` | `inline code` |
| three backticks | Code block (language hint supported) |
| `[text](https://example.com)` | [text](https://example.com) |
| `![alt](image-url)` | Image |
| `> quote` | Blockquote |
| `- item` / `1. item` | Unordered / ordered list |
| `- [ ] todo` | Task list |
| \| col1 \| col2 \| | Table |
| `---` | Horizontal rule |

> Tip: the editor toolbar covers all of the above (the "H" dropdown offers H1-H6) — select text and click to insert.

*— WangHai Server Wiki*
"""

# ---------------------------------------------------------------------------
# 表结构
# ---------------------------------------------------------------------------

WIKI_PAGE_TABLE_COLUMNS: dict[str, str] = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "slug": "TEXT NOT NULL UNIQUE",          # 页面路径：小写 ASCII 段，/ 分隔层级
    "title_zh": "TEXT NOT NULL DEFAULT ''",  # 中文标题（保存时从 H1 自动提取）
    "content_zh": "TEXT NOT NULL DEFAULT ''",  # 中文 Markdown 原文
    "title_en": "TEXT NOT NULL DEFAULT ''",  # 英文标题
    "content_en": "TEXT NOT NULL DEFAULT ''",  # 英文 Markdown 原文
    "min_permission": "INTEGER NOT NULL DEFAULT 2",  # 该页最小编辑权限（2/3/4）
    "disambig": "INTEGER NOT NULL DEFAULT 0",  # 1 = 消歧义页（列出名称相近的多个条目）
    "author_uid": "INTEGER NOT NULL",        # 创建者 uid
    "updated_by_uid": "INTEGER NOT NULL",    # 最后编辑者 uid
    "created_at": "TEXT NOT NULL",           # ISO 8601
    "updated_at": "TEXT NOT NULL",           # ISO 8601（任一语言最近一次编辑）
}

WIKI_REVISION_TABLE_COLUMNS: dict[str, str] = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "page_id": "INTEGER NOT NULL",           # -> pages.id
    "lang": "TEXT NOT NULL",                 # 'zh' / 'en'
    "rev_no": "INTEGER NOT NULL",            # 每种语言自 1 起递增
    "title": "TEXT NOT NULL",                # 该修订时的标题快照
    "content": "TEXT NOT NULL",              # 该修订时的 Markdown 快照
    "summary": "TEXT",                       # 编辑摘要，可空
    "author_uid": "INTEGER NOT NULL",
    "created_at": "TEXT NOT NULL",
}

WIKI_REDIRECT_TABLE_COLUMNS: dict[str, str] = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "from_slug": "TEXT NOT NULL UNIQUE",     # 旧路径（重定向来源，不能是现有页面）
    "to_slug": "TEXT NOT NULL",              # 目标路径（可继续指向另一重定向，解析时限制步数）
    "created_at": "TEXT NOT NULL",
}

# FTS5 全文索引表（trigram 分词：支持中英文 3 字符及以上子串匹配）。
WIKI_FTS_TABLE = "wiki_fts"

# ---------------------------------------------------------------------------
# 纯函数：slug / 语言校验、标题提取
# ---------------------------------------------------------------------------


def validate_slug(slug: str) -> str:
    """校验 slug；不合法时抛出 :class:`WikiSlugInvalidError`。"""
    if not isinstance(slug, str):
        raise WikiSlugInvalidError(f"slug 必须是字符串，收到 {type(slug).__name__}")
    slug = slug.strip()
    if not slug or len(slug) > SLUG_MAX_LENGTH or SLUG_PATTERN.fullmatch(slug) is None:
        raise WikiSlugInvalidError(
            f"slug {slug!r} 不合法：仅允许小写字母/数字/短横线组成的路径段（以 / 分隔）"
        )
    return slug


def validate_lang(lang: str) -> str:
    """规范化语言参数；非法时抛出 :class:`WikiLangInvalidError`。"""
    if not isinstance(lang, str):
        raise WikiLangInvalidError(f"语言必须是字符串，收到 {type(lang).__name__}")
    lang = lang.strip().lower()
    if lang not in LANGS:
        raise WikiLangInvalidError(f"不支持的语言：{lang!r}")
    return lang


def validate_min_permission(value) -> int:
    """校验页面最小编辑权限（2/3/4）；非法时抛出 :class:`WikiPermissionInvalidError`。"""
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise WikiPermissionInvalidError(f"权限值 {value!r} 不合法：应为 2/3/4") from None
    if value not in MIN_PERMISSIONS:
        raise WikiPermissionInvalidError(f"权限值 {value!r} 不合法：应为 2/3/4")
    return value


def extract_wiki_title(markdown: str) -> str:
    """从 Markdown 中提取页面标题：第一个 ATX 一级标题（``# ``）的文本。

    剥离标题行内的链接 / 图片 / 行内代码 / 加粗 / 斜体标记，
    无一级标题或提取为空时返回空字符串（由调用方回退为 slug）。
    """
    if not isinstance(markdown, str):
        return ""
    for line in markdown.splitlines():
        m = re.match(r"^\s*#(?!#)\s+(.*?)\s*$", line)
        if not m:
            continue
        text = m.group(1).strip()
        # 图片 ![alt](url) -> alt
        text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
        # 链接 [text](url) -> text
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
        # 行内代码 `x` -> x
        text = re.sub(r"`([^`]*)`", r"\1", text)
        # 加粗 / 斜体标记
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"__([^_]+)__", r"\1", text)
        text = re.sub(r"_([^_]+)_", r"\1", text)
        text = re.sub(r"~~([^~]+)~~", r"\1", text)
        text = text.strip()
        if text:
            return text[:MAX_TITLE_LENGTH]
    return ""


# ---------------------------------------------------------------------------
# 错误类型与双语消息
# ---------------------------------------------------------------------------


class WikiDatabaseError(Exception):
    """维基数据库相关错误的基类，携带稳定的错误码 ``code``。"""

    code = "wiki_database_error"


class WikiSlugInvalidError(WikiDatabaseError):
    """slug 不满足 :data:`SLUG_PATTERN`。"""

    code = "wiki_slug_invalid"


class WikiLangInvalidError(WikiDatabaseError):
    """语言不在 :data:`LANGS` 中。"""

    code = "wiki_lang_invalid"


class WikiPageNotFoundError(WikiDatabaseError):
    """指定页面不存在。"""

    code = "wiki_page_not_found"


class WikiSlugExistsError(WikiDatabaseError):
    """slug 已被占用。"""

    code = "wiki_slug_exists"


class WikiContentEmptyError(WikiDatabaseError):
    """页面内容为空。"""

    code = "wiki_content_empty"


class WikiContentTooLargeError(WikiDatabaseError):
    """页面内容超过上限。"""

    code = "wiki_content_too_large"


class WikiPermissionInvalidError(WikiDatabaseError):
    """页面最小编辑权限取值不合法（应为 2/3/4）。"""

    code = "wiki_permission_invalid"


class WikiRevisionConflictError(WikiDatabaseError):
    """乐观锁冲突：base_rev 与当前语言的修订号不符。"""

    code = "wiki_revision_conflict"


class WikiRevisionNotFoundError(WikiDatabaseError):
    """指定修订不存在。"""

    code = "wiki_revision_not_found"


class WikiPageHasChildrenError(WikiDatabaseError):
    """页面存在子页面，禁止删除（防止产生孤儿子树）。"""

    code = "wiki_page_has_children"


class WikiRedirectInvalidError(WikiDatabaseError):
    """重定向不合法（来源是现有页面 / 指向自身 / 形成循环）。"""

    code = "wiki_redirect_invalid"


# 错误码 -> 双语消息（与全站 title_suffix 的 zh/en 结构保持一致）。
ERROR_MESSAGES: dict[str, dict[str, str]] = {
    "wiki_page_not_found": {
        "zh": "页面不存在",
        "en": "Page not found",
    },
    "wiki_slug_invalid": {
        "zh": "页面路径不合法：仅允许小写字母、数字、短横线和斜杠",
        "en": "Invalid page path: lowercase letters, digits, hyphens and slashes only",
    },
    "wiki_lang_invalid": {
        "zh": "不支持的语言",
        "en": "Unsupported language",
    },
    "wiki_slug_exists": {
        "zh": "页面路径已存在",
        "en": "Page path already exists",
    },
    "wiki_content_empty": {
        "zh": "页面内容不能为空",
        "en": "Page content cannot be empty",
    },
    "wiki_content_too_large": {
        "zh": "页面内容过大（不能超过 200KB）",
        "en": "Page content is too large (200KB max)",
    },
    "wiki_permission_invalid": {
        "zh": "页面编辑权限取值不合法（应为 2/3/4）",
        "en": "Invalid page edit permission (must be 2, 3 or 4)",
    },
    "wiki_revision_conflict": {
        "zh": "页面已被他人修改，请刷新后重试",
        "en": "The page has been modified by someone else, please refresh and retry",
    },
    "wiki_revision_not_found": {
        "zh": "修订记录不存在",
        "en": "Revision not found",
    },
    "wiki_page_has_children": {
        "zh": "该页面存在子页面，无法删除",
        "en": "This page has child pages and cannot be deleted",
    },
    "wiki_upload_unsupported": {
        "zh": "不支持的文件类型（仅支持图片 / 视频 / 音频）",
        "en": "Unsupported file type (images / videos / audio only)",
    },
    "wiki_upload_too_large": {
        "zh": "文件过大（图片 5MB / 视频 50MB / 音频 20MB）",
        "en": "File too large (images 5MB / videos 50MB / audio 20MB)",
    },
    "wiki_upload_not_found": {
        "zh": "文件不存在",
        "en": "File not found",
    },
    "wiki_redirect_invalid": {
        "zh": "重定向不合法：来源不能是现有页面，且不能指向自身或形成循环",
        "en": "Invalid redirect: source must not be an existing page, and cannot point to itself or form a loop",
    },
    "wiki_redirect_not_found": {
        "zh": "重定向不存在",
        "en": "Redirect not found",
    },
}


# ---------------------------------------------------------------------------
# 数据库实现
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _escape_like(text: str) -> str:
    """转义 LIKE 通配符，使搜索词按字面匹配。"""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _strip_markdown(text: str) -> str:
    """粗略剥离 Markdown 标记，用于搜索片段展示。"""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"[#>*_~|-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _make_snippet(content: str, query: str, radius: int = 60) -> str:
    """从 Markdown 原文中提取命中片段（大小写不敏感，取首个命中位置附近文本）。"""
    text = _strip_markdown(content)
    lower = text.lower()
    q = query.lower()
    idx = lower.find(q)
    if idx < 0:
        idx = 0
    start = max(0, idx - radius)
    end = min(len(text), idx + len(q) + radius)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def _content_col(lang: str) -> str:
    """语言 -> pages 表内容列名。"""
    return f"content_{validate_lang(lang)}"


def _title_col(lang: str) -> str:
    """语言 -> pages 表标题列名。"""
    return f"title_{validate_lang(lang)}"


class WikiDatabase(UserDatabase):
    """存储维基页面与修订的 sqlite3 数据库。

    对应数据库文件 ``wiki.db``，内部表 ``pages``（当前版本，双语）+ ``revisions``
    （按语言的历史快照）。全部内容（含 Markdown 原文）存于 SQLite，不落盘为文件。
    """

    TABLE_NAME = "pages"
    TABLE_COLUMNS = WIKI_PAGE_TABLE_COLUMNS
    REVISION_TABLE_NAME = "revisions"
    REDIRECT_TABLE_NAME = "redirects"

    def __init__(self, database_path: str = "wiki.db") -> None:
        super().__init__(database_path)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """打开数据库，确保 pages + revisions + redirects 表存在；兼容旧单语库；空库播种欢迎页。"""
        super().connect()
        self.create_table(
            self.REVISION_TABLE_NAME, WIKI_REVISION_TABLE_COLUMNS, if_not_exists=True
        )
        self.create_table(
            self.REDIRECT_TABLE_NAME, WIKI_REDIRECT_TABLE_COLUMNS, if_not_exists=True
        )
        self._migrate_languages()
        self._seed_welcome()
        self._refresh_welcome_seed()
        self.rebuild_auto_disambig()
        self._sync_fts()

    def _migrate_languages(self) -> None:
        """把旧版单语 schema 迁移为双语 schema（幂等，可重复执行）。

        - revisions 表补充 ``lang`` 列（旧数据默认归入 zh）；
        - pages 表若存在旧 ``content`` / ``title`` 列，把内容复制到
          ``content_zh`` / ``title_zh`` 并尝试删除旧列（SQLite >= 3.35）。
        """
        # 1) revisions.lang
        rev_cols = {
            row["name"]
            for row in self._conn.execute(
                f"PRAGMA table_info({self.REVISION_TABLE_NAME})"
            ).fetchall()
        }
        if "lang" not in rev_cols:
            self._conn.execute(
                f"ALTER TABLE {self.REVISION_TABLE_NAME} "
                f"ADD COLUMN lang TEXT NOT NULL DEFAULT 'zh'"
            )
        # 2) pages 旧列迁移（新列已由 UserDatabase._migrate 补充）
        page_cols = {
            row["name"]
            for row in self._conn.execute(
                f"PRAGMA table_info({self.TABLE_NAME})"
            ).fetchall()
        }
        if "content" in page_cols and "content_zh" in page_cols:
            self._conn.execute(
                f"UPDATE {self.TABLE_NAME} SET content_zh = content, title_zh = title "
                f"WHERE content_zh = '' OR content_zh IS NULL"
            )
            for col in ("content", "title", "rev_no"):
                if col in page_cols:
                    try:
                        self._conn.execute(
                            f"ALTER TABLE {self.TABLE_NAME} DROP COLUMN {col}"
                        )
                    except sqlite3.OperationalError:
                        pass  # 旧版 SQLite 不支持 DROP COLUMN，保留旧列（无碍）
        self._conn.commit()

    def _seed_welcome(self) -> None:
        """pages 为空时写入欢迎页（双语，首次启动体验）。"""
        row = self._conn.execute(
            f"SELECT id FROM {self.TABLE_NAME} LIMIT 1"
        ).fetchone()
        if row is not None:
            return
        self.create_page(WELCOME_SLUG, WELCOME_CONTENT_ZH, author_uid=0, lang="zh")
        self.update_page(
            WELCOME_SLUG, WELCOME_CONTENT_EN, author_uid=0, lang="en", base_rev=None
        )

    def _refresh_welcome_seed(self) -> None:
        """把旧版欢迎页种子内容升级为新版（幂等，可重复执行）。

        仅当欢迎页仍为**纯系统播种**（不存在 author_uid != 0 的修订，即未被
        真实用户编辑过）且内容与最新种子不一致时，就地更新 pages 行与两种
        语言的最新修订快照——不新增修订记录，也不覆盖用户的任何改动。
        """
        page = self.get_page(WELCOME_SLUG)
        if page is None:
            return
        if (
            page.get("content_zh") == WELCOME_CONTENT_ZH
            and page.get("content_en") == WELCOME_CONTENT_EN
        ):
            return  # 已是最新种子
        row = self._conn.execute(
            f"SELECT COUNT(*) AS n FROM {self.REVISION_TABLE_NAME} "
            f"WHERE page_id = ? AND author_uid != 0",
            (page["id"],),
        ).fetchone()
        if row and row["n"]:
            return  # 已被真实用户编辑过，保留其内容
        title_zh = extract_wiki_title(WELCOME_CONTENT_ZH) or WELCOME_SLUG
        title_en = extract_wiki_title(WELCOME_CONTENT_EN) or WELCOME_SLUG
        self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET title_zh = ?, content_zh = ?, "
            f"title_en = ?, content_en = ?, updated_at = ? WHERE id = ?",
            (title_zh, WELCOME_CONTENT_ZH, title_en, WELCOME_CONTENT_EN, _now(), page["id"]),
        )
        for lang, content, title in (
            ("zh", WELCOME_CONTENT_ZH, title_zh),
            ("en", WELCOME_CONTENT_EN, title_en),
        ):
            latest = self._conn.execute(
                f"SELECT id FROM {self.REVISION_TABLE_NAME} "
                f"WHERE page_id = ? AND lang = ? ORDER BY rev_no DESC LIMIT 1",
                (page["id"], lang),
            ).fetchone()
            if latest is not None:
                self._conn.execute(
                    f"UPDATE {self.REVISION_TABLE_NAME} SET title = ?, content = ? WHERE id = ?",
                    (title, content, latest["id"]),
                )
        self._conn.commit()

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _get_page_row(self, *, page_id: int | None = None, slug: str | None = None):
        """按 id 或 slug 查询页面行；不存在返回 None。"""
        if page_id is not None:
            return self._conn.execute(
                f"SELECT * FROM {self.TABLE_NAME} WHERE id = ?", (page_id,)
            ).fetchone()
        if slug is not None:
            return self._conn.execute(
                f"SELECT * FROM {self.TABLE_NAME} WHERE slug = ?", (slug,)
            ).fetchone()
        return None

    def _current_rev_no(self, page_id: int, lang: str) -> int:
        """某页面某语言的当前修订号（无修订时为 0）。"""
        lang = validate_lang(lang)
        row = self._conn.execute(
            f"SELECT COALESCE(MAX(rev_no), 0) AS n FROM {self.REVISION_TABLE_NAME} "
            f"WHERE page_id = ? AND lang = ?",
            (page_id, lang),
        ).fetchone()
        return int(row["n"]) if row else 0

    def _insert_revision(
        self, page_id: int, lang: str, rev_no: int, title: str, content: str,
        summary: str | None, author_uid: int,
    ) -> int:
        """写入一条修订快照并修剪超出上限的最旧修订，返回修订 id。"""
        lang = validate_lang(lang)
        cursor = self._conn.execute(
            f"INSERT INTO {self.REVISION_TABLE_NAME} "
            f"(page_id, lang, rev_no, title, content, summary, author_uid, created_at) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (page_id, lang, rev_no, title, content, summary, author_uid, _now()),
        )
        # 修剪：每页每语言仅保留最新的 MAX_REVISIONS 条
        self._conn.execute(
            f"DELETE FROM {self.REVISION_TABLE_NAME} WHERE page_id = ? AND lang = ? "
            f"AND rev_no NOT IN ("
            f"SELECT rev_no FROM {self.REVISION_TABLE_NAME} WHERE page_id = ? AND lang = ? "
            f"ORDER BY rev_no DESC LIMIT ?)",
            (page_id, lang, page_id, lang, MAX_REVISIONS),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def _apply_update(
        self, page: dict[str, Any], content: str, lang: str,
        summary: str | None, author_uid: int,
    ) -> dict[str, Any]:
        """以新内容（指定语言）生成下一个修订并更新 pages 行，返回更新后的页面字典。"""
        lang = validate_lang(lang)
        title = extract_wiki_title(content) or page["slug"]
        rev_no = self._current_rev_no(page["id"], lang) + 1
        content_col = _content_col(lang)
        title_col = _title_col(lang)
        self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET {title_col} = ?, {content_col} = ?, "
            f"updated_by_uid = ?, updated_at = ? WHERE id = ?",
            (title, content, author_uid, _now(), page["id"]),
        )
        self._insert_revision(page["id"], lang, rev_no, title, content, summary, author_uid)
        return self.get_page_by_id(page["id"])

    # ------------------------------------------------------------------
    # 页面业务方法
    # ------------------------------------------------------------------

    def create_page(
        self, slug: str, content: str, author_uid: int, lang: str = "zh",
        *, min_permission: int = DEFAULT_MIN_PERMISSION, disambig: bool = False,
    ) -> dict[str, Any]:
        """创建页面（指定语言，修订号 1）并写入第一条修订快照，返回新页面字典。

        :param min_permission: 该页的最小编辑权限（2/3/4，默认 2）。
        :param disambig: 是否为消歧义页。
        :raises WikiSlugInvalidError / WikiLangInvalidError / WikiSlugExistsError /
                WikiContentEmptyError / WikiContentTooLargeError /
                WikiPermissionInvalidError
        """
        slug = validate_slug(slug)
        lang = validate_lang(lang)
        min_permission = validate_min_permission(min_permission)
        if not isinstance(content, str) or not content.strip():
            raise WikiContentEmptyError("页面内容不能为空")
        if len(content) > MAX_CONTENT_LENGTH:
            raise WikiContentTooLargeError("页面内容超过上限")
        if self._get_page_row(slug=slug) is not None:
            raise WikiSlugExistsError(f"slug {slug!r} 已存在")
        title = extract_wiki_title(content) or slug
        now = _now()
        content_col = _content_col(lang)
        title_col = _title_col(lang)
        cursor = self._conn.execute(
            f"INSERT INTO {self.TABLE_NAME} "
            f"(slug, {title_col}, {content_col}, min_permission, disambig, "
            f"author_uid, updated_by_uid, created_at, updated_at) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (slug, title, content, min_permission, 1 if disambig else 0,
             author_uid, author_uid, now, now),
        )
        page_id = int(cursor.lastrowid)
        self._insert_revision(page_id, lang, 1, title, content, "", author_uid)
        self.rebuild_auto_disambig()  # 新页面可能引发标题歧义
        self._sync_fts()
        return self.get_page_by_id(page_id)

    def get_page(self, slug: str) -> dict[str, Any] | None:
        """按 slug 读取页面（含两种语言的内容）；不存在返回 None。"""
        if not isinstance(slug, str) or not slug:
            return None
        return self._row_to_dict(self._get_page_row(slug=slug))

    def get_page_by_id(self, page_id: int) -> dict[str, Any] | None:
        """按 id 读取页面；不存在返回 None。"""
        return self._row_to_dict(self._get_page_row(page_id=page_id))

    def update_page(
        self, slug: str, content: str, author_uid: int, lang: str = "zh",
        *, base_rev: int | None = None, summary: str | None = None,
        disambig: bool | None = None,
    ) -> dict[str, Any]:
        """更新页面指定语言的内容（乐观锁），返回更新后的页面字典。

        :param base_rev: 调用方基于的修订号；与当前语言修订号不符时抛
            :class:`WikiRevisionConflictError`（None 表示不校验）。
        :param disambig: 是否更新消歧义标记（None 表示保持不变）。
        :raises WikiPageNotFoundError / WikiContentEmptyError /
                WikiContentTooLargeError / WikiRevisionConflictError
        """
        lang = validate_lang(lang)
        page = self.get_page(slug)
        if page is None:
            raise WikiPageNotFoundError(f"页面 {slug!r} 不存在")
        if not isinstance(content, str) or not content.strip():
            raise WikiContentEmptyError("页面内容不能为空")
        if len(content) > MAX_CONTENT_LENGTH:
            raise WikiContentTooLargeError("页面内容超过上限")
        current = self._current_rev_no(page["id"], lang)
        if base_rev is not None and int(base_rev) != current:
            raise WikiRevisionConflictError(
                f"base_rev={base_rev} 与 {lang} 当前 rev_no={current} 不符"
            )
        page = self._apply_update(page, content, lang, summary, author_uid)
        if disambig is not None:
            self._conn.execute(
                f"UPDATE {self.TABLE_NAME} SET disambig = ? WHERE id = ?",
                (1 if disambig else 0, page["id"]),
            )
            self._conn.commit()
            page = self.get_page_by_id(page["id"])
        self.rebuild_auto_disambig()  # 标题变更可能引发/消除歧义
        self._sync_fts()
        return page

    def set_min_permission(self, slug: str, value) -> dict[str, Any]:
        """调整页面的最小编辑权限（2/3/4），返回更新后的页面字典。

        :raises WikiPageNotFoundError / WikiPermissionInvalidError
        """
        page = self.get_page(slug)
        if page is None:
            raise WikiPageNotFoundError(f"页面 {slug!r} 不存在")
        value = validate_min_permission(value)
        self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET min_permission = ? WHERE id = ?",
            (value, page["id"]),
        )
        self._conn.commit()
        return self.get_page_by_id(page["id"])

    def delete_page(self, slug: str) -> bool:
        """删除页面及其全部修订；存在子页面时抛 :class:`WikiPageHasChildrenError`。"""
        page = self.get_page(slug)
        if page is None:
            raise WikiPageNotFoundError(f"页面 {slug!r} 不存在")
        prefix = _escape_like(page["slug"]) + "/%"
        child = self._conn.execute(
            f"SELECT id FROM {self.TABLE_NAME} WHERE slug LIKE ? ESCAPE '\\' LIMIT 1",
            (prefix,),
        ).fetchone()
        if child is not None:
            raise WikiPageHasChildrenError(f"页面 {slug!r} 存在子页面，禁止删除")
        self._conn.execute(
            f"DELETE FROM {self.REVISION_TABLE_NAME} WHERE page_id = ?", (page["id"],)
        )
        self._conn.execute(
            f"DELETE FROM {self.TABLE_NAME} WHERE id = ?", (page["id"],)
        )
        self._conn.commit()
        self.rebuild_auto_disambig()  # 删除页面可能消除歧义
        self._sync_fts()
        return True

    # ------------------------------------------------------------------
    # 重定向（页面改名后旧路径自动跳转）
    # ------------------------------------------------------------------

    def create_redirect(self, from_slug: str, to_slug: str) -> dict[str, Any]:
        """创建（或覆盖）一条重定向：旧路径 -> 新路径。

        :raises WikiSlugInvalidError / WikiRedirectInvalidError:
            来源是现有页面、指向自身或形成循环时拒绝。
        """
        from_slug = validate_slug(from_slug)
        to_slug = validate_slug(to_slug)
        if from_slug == to_slug:
            raise WikiRedirectInvalidError("重定向不能指向自身")
        if self._get_page_row(slug=from_slug) is not None:
            raise WikiRedirectInvalidError("重定向来源不能是现有页面")
        # 循环检测：从 to_slug 沿重定向链行走，若回到 from_slug 则拒绝（覆盖多跳回路）
        seen: set[str] = {from_slug}
        current = to_slug
        for _ in range(8):
            if current == from_slug:
                raise WikiRedirectInvalidError("重定向不能形成循环")
            if current in seen:
                break
            seen.add(current)
            row = self._conn.execute(
                f"SELECT to_slug FROM {self.REDIRECT_TABLE_NAME} WHERE from_slug = ?",
                (current,),
            ).fetchone()
            if row is None:
                break
            current = row["to_slug"]
        now = _now()
        self._conn.execute(
            f"INSERT INTO {self.REDIRECT_TABLE_NAME} (from_slug, to_slug, created_at) "
            f"VALUES (?, ?, ?) "
            f"ON CONFLICT(from_slug) DO UPDATE SET to_slug = ?, created_at = ?",
            (from_slug, to_slug, now, to_slug, now),
        )
        self._conn.commit()
        return {"from_slug": from_slug, "to_slug": to_slug}

    def resolve_redirect(self, slug: str, max_steps: int = 8) -> str | None:
        """解析重定向链，返回最终目标路径；不存在重定向或形成循环时返回 None。"""
        if not isinstance(slug, str) or not slug:
            return None
        seen: set[str] = set()
        current = slug
        for _ in range(max_steps):
            row = self._conn.execute(
                f"SELECT to_slug FROM {self.REDIRECT_TABLE_NAME} WHERE from_slug = ?",
                (current,),
            ).fetchone()
            if row is None:
                return current if current != slug else None
            current = row["to_slug"]
            if current in seen:
                return None  # 循环
            seen.add(current)
        return None

    def delete_redirect(self, from_slug: str) -> bool:
        """删除一条重定向，返回是否真的删除了。"""
        cursor = self._conn.execute(
            f"DELETE FROM {self.REDIRECT_TABLE_NAME} WHERE from_slug = ?", (from_slug,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def list_redirects(self) -> list[dict[str, Any]]:
        """返回全部重定向列表。"""
        rows = self._conn.execute(
            f"SELECT from_slug, to_slug, created_at FROM {self.REDIRECT_TABLE_NAME} "
            f"ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    # ------------------------------------------------------------------
    # 系统自动消歧义页（作者 uid 0）
    # ------------------------------------------------------------------

    @staticmethod
    def _slugify_title(title: str) -> str:
        """标题 -> 可用的 ASCII slug（用于 disambig/ 分组）；无法 slug 化时返回空。"""
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return slug[:100]

    @staticmethod
    def _build_disambig_content(term: str, lang: str, items: list) -> str:
        """生成消歧义页 Markdown（列出全部同名条目链接）。"""
        term_zh = lang == "zh"
        lines = [f"# {term}{'（消歧义）' if term_zh else ' (disambiguation)'}", ""]
        if term_zh:
            lines.append(f"名称为「{term}」的条目有多个，请根据描述选择前往：")
        else:
            lines.append(f'Multiple entries share the title "{term}". Pick the one you meant:')
        lines.append("")
        for slug, title in items:
            safe = title.replace("[", "\\[").replace("]", "\\]")
            lines.append(f"- [{safe}](/wiki/page/{slug}) —— `{slug}`")
        lines.append("")
        lines.append(
            "*本页面由系统自动构建，可编辑或删除。*"
            if term_zh
            else "*This page was auto-generated by the system; edit or delete it freely.*"
        )
        return "\n".join(lines)

    def _is_system_owned(self, page_id: int) -> bool:
        """页面是否纯系统所有（全部修订作者均为 uid 0）。"""
        row = self._conn.execute(
            f"SELECT COUNT(*) AS n FROM {self.REVISION_TABLE_NAME} "
            f"WHERE page_id = ? AND author_uid != 0",
            (page_id,),
        ).fetchone()
        return not (row and row["n"])

    def _create_system_page_raw(self, slug: str, content: str, lang: str, summary: str) -> dict:
        """以 uid 0 直接建页（绕过 create_page，避免递归触发重建）。"""
        lang = validate_lang(lang)
        title = extract_wiki_title(content) or slug
        now = _now()
        content_col = _content_col(lang)
        title_col = _title_col(lang)
        cursor = self._conn.execute(
            f"INSERT INTO {self.TABLE_NAME} "
            f"(slug, {title_col}, {content_col}, min_permission, disambig, "
            f"author_uid, updated_by_uid, created_at, updated_at) "
            f"VALUES (?, ?, ?, 2, 1, 0, 0, ?, ?)",
            (slug, title, content, now, now),
        )
        page_id = int(cursor.lastrowid)
        self._insert_revision(page_id, lang, 1, title, content, summary, 0)
        return self.get_page_by_id(page_id)

    def _delete_page_raw(self, page_id: int) -> None:
        """直接删除页面与修订（绕过 delete_page，避免递归触发重建）。"""
        self._conn.execute(
            f"DELETE FROM {self.REVISION_TABLE_NAME} WHERE page_id = ?", (page_id,)
        )
        self._conn.execute(f"DELETE FROM {self.TABLE_NAME} WHERE id = ?", (page_id,))
        self._conn.commit()

    def rebuild_auto_disambig(self) -> dict[str, int]:
        """自动构建 / 更新 / 清理系统消歧义页（作者 uid 0），返回统计。

        原理：
        - 扫描全部页面，按语言分组统计**规范化标题相同且 slug 不同**的条目
          （≥2 个即视为歧义项；消歧义页自身与对应语言内容为空的页面不参与）；
        - 每个歧义项生成一个系统消歧义页：slug 为 ``disambig/<标题slug化>``
          （中文等无法 slug 化时用 sha1 前缀；与人工页面冲突自动加序号），
          内容列出全部同名条目链接，标记 ``disambig=1``；
        - **仅更新纯系统所有**（全部修订作者为 uid 0）的自动页；被人工编辑
          过的页面系统不再接管；歧义消失（< 2 个候选）时删除失效的系统自动页。
        """
        stats = {"created": 0, "updated": 0, "deleted": 0}
        pages = self.list_pages()

        # 1) 按语言收集歧义候选
        by_title = {"zh": defaultdict(list), "en": defaultdict(list)}
        for p in pages:
            if p["disambig"]:
                continue
            for lang in ("zh", "en"):
                title = (p.get(f"title_{lang}") or "").strip()
                if p.get(f"has_{lang}") and title:
                    by_title[lang][title].append((p["slug"], title))

        needed = []  # (term, lang, items)
        for lang in ("zh", "en"):
            for term, items in by_title[lang].items():
                if len({slug for slug, _ in items}) >= 2:
                    needed.append((term, lang, items))

        # 2) 现有纯系统自动页（需完整行以比对内容）+ 人工接管的消歧义页标题
        existing = {}
        human_disambig_titles = {"zh": set(), "en": set()}
        for p in pages:
            if not p["slug"].startswith("disambig/") or not p["disambig"]:
                continue
            if self._is_system_owned(p["id"]):
                existing[p["slug"]] = self.get_page(p["slug"])
            else:
                # 人工接管：系统不再为其对应词条重复构建
                for lang in ("zh", "en"):
                    title = (p.get(f"title_{lang}") or "").strip()
                    if title:
                        human_disambig_titles[lang].add(title)

        # 3) 为每个歧义项确定 slug（复用已有系统页；与人工页面冲突则加序号）
        planned = []
        used_slugs = set(existing.keys())
        for term, lang, items in needed:
            expected_title = (
                f"{term}（消歧义）" if lang == "zh" else f"{term} (disambiguation)"
            )
            if expected_title in human_disambig_titles[lang]:
                continue  # 词条已有消歧义页（人工接管），系统不再重复构建
            base = self._slugify_title(term)
            if not base:
                base = f"term-{hashlib.sha1(term.encode('utf-8')).hexdigest()[:8]}"
            slug = f"disambig/{base}"
            if slug not in used_slugs:
                candidate = slug
                n = 2
                while self._get_page_row(slug=candidate) is not None and n < 30:
                    candidate = f"disambig/{base}-{n}"
                    n += 1
                if self._get_page_row(slug=candidate) is not None:
                    continue  # 序号耗尽，跳过该歧义项
                slug = candidate
                used_slugs.add(slug)
            planned.append((term, lang, items, slug))

        # 4) 创建 / 更新
        planned_slugs = {item[3] for item in planned}
        for term, lang, items, slug in planned:
            content = self._build_disambig_content(term, lang, items)
            if slug in existing:
                page = existing[slug]
                if page.get(f"content_{lang}") == content:
                    continue  # 内容未变，不产生新修订
                self._apply_update(page, content, lang, "系统自动更新消歧义列表", 0)
                stats["updated"] += 1
            else:
                self._create_system_page_raw(slug, content, lang, "系统自动构建消歧义页")
                stats["created"] += 1

        # 5) 清理失效自动页（歧义已消失）
        for slug, page in existing.items():
            if slug not in planned_slugs:
                self._delete_page_raw(page["id"])
                stats["deleted"] += 1

        self._sync_fts()  # 自动页的原始写入同步索引
        return stats

    def list_pages(self) -> list[dict[str, Any]]:
        """返回全部页面的列表元信息（不含正文，含双语标题、语言可用性、最小编辑权限与消歧义标记），按 slug 排序。"""
        rows = self._conn.execute(
            f"SELECT id, slug, title_zh, title_en, min_permission, disambig, "
            f"author_uid, updated_by_uid, created_at, updated_at, "
            f"CASE WHEN content_zh = '' THEN 0 ELSE 1 END AS has_zh, "
            f"CASE WHEN content_en = '' THEN 0 ELSE 1 END AS has_en "
            f"FROM {self.TABLE_NAME} ORDER BY slug"
        ).fetchall()
        result = []
        for row in rows:
            item = self._row_to_dict(row)
            item["has_zh"] = bool(item["has_zh"])
            item["has_en"] = bool(item["has_en"])
            item["disambig"] = bool(item["disambig"])
            result.append(item)
        return result

    def count_pages(self) -> int:
        """返回页面总数。"""
        row = self._conn.execute(f"SELECT COUNT(*) AS n FROM {self.TABLE_NAME}").fetchone()
        return int(row["n"]) if row else 0

    def search_pages(self, query: str, lang: str = "zh", limit: int = 50) -> list[dict[str, Any]]:
        """对指定语言的标题 + 正文搜索，标题命中优先。

        优先走 FTS5（trigram 分词，支持中英文 3 字符及以上子串匹配 + BM25 相关性排序）；
        查询过短（< 3 字符）或 FTS 不可用时回退 LIKE 子串匹配（大小写不敏感）。

        返回条目含 ``id/slug/title/author_uid/updated_by_uid/updated_at/snippet``。
        """
        lang = validate_lang(lang)
        q = (query or "").strip()
        if not q:
            return []
        results = self._fts_search(q, lang, limit)
        if results is not None:
            return results
        like = f"%{_escape_like(q)}%"
        title_col = _title_col(lang)
        content_col = _content_col(lang)
        rows = self._conn.execute(
            f"SELECT id, slug, {title_col} AS title, author_uid, updated_by_uid, "
            f"updated_at, {content_col} AS content FROM {self.TABLE_NAME} "
            f"WHERE {title_col} LIKE ? ESCAPE '\\' OR {content_col} LIKE ? ESCAPE '\\' "
            f"ORDER BY ({title_col} LIKE ? ESCAPE '\\') DESC, updated_at DESC LIMIT ?",
            (like, like, like, limit),
        ).fetchall()
        results = []
        for row in rows:
            item = self._row_to_dict(row)
            item.pop("content", None)
            item["snippet"] = _make_snippet(row["content"], q)
            results.append(item)
        return results

    # ------------------------------------------------------------------
    # FTS5 全文索引
    # ------------------------------------------------------------------

    def _sync_fts(self) -> None:
        """重建 FTS5 索引（全量：清空后从 pages 表重灌；页面量小，成本可忽略）。"""
        try:
            self._conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {WIKI_FTS_TABLE} USING fts5("
                f"slug UNINDEXED, title_zh, content_zh, title_en, content_en, "
                f"tokenize='trigram')"
            )
            self._conn.execute(f"DELETE FROM {WIKI_FTS_TABLE}")
            self._conn.execute(
                f"INSERT INTO {WIKI_FTS_TABLE} (slug, title_zh, content_zh, title_en, content_en) "
                f"SELECT slug, title_zh, content_zh, title_en, content_en FROM {self.TABLE_NAME}"
            )
            self._conn.commit()
        except sqlite3.OperationalError:
            # FTS5 不可用（如平台未编译）时静默降级，搜索走 LIKE
            pass

    def _fts_search(self, q: str, lang: str, limit: int) -> list[dict[str, Any]] | None:
        """FTS5 trigram 搜索；失败或查询过短返回 None（由调用方回退 LIKE）。"""
        if len(q) < 3:
            return None
        try:
            title_col = _title_col(lang)
            content_col = _content_col(lang)
            # 短语查询：内部双引号翻倍转义；列限定为当前语言的标题/正文
            phrase = '"' + q.replace('"', '""') + '"'
            match_sql = f"{title_col} : {phrase} OR {content_col} : {phrase}"
            # BM25 列权重：标题 5、正文 1、其余 0（列序：slug, title_zh, content_zh, title_en, content_en）
            weights = "0, 5, 1, 0, 0" if lang == "zh" else "0, 0, 0, 5, 1"
            rows = self._conn.execute(
                f"SELECT slug, bm25({WIKI_FTS_TABLE}, {weights}) AS score "
                f"FROM {WIKI_FTS_TABLE} WHERE {WIKI_FTS_TABLE} MATCH ? "
                f"ORDER BY score LIMIT ?",
                (match_sql, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return None
        results = []
        for row in rows:
            page = self.get_page(row["slug"])
            if page is None:
                continue
            content = page.get(f"content_{lang}") or ""
            results.append({
                "id": page["id"],
                "slug": page["slug"],
                "title": page.get(f"title_{lang}") or "",
                "author_uid": page["author_uid"],
                "updated_by_uid": page["updated_by_uid"],
                "updated_at": page["updated_at"],
                "snippet": _make_snippet(content, q),
            })
        return results

    # ------------------------------------------------------------------
    # 修订业务方法
    # ------------------------------------------------------------------

    def list_revisions(self, page_id: int, lang: str = "zh", limit: int = MAX_REVISIONS) -> list[dict[str, Any]]:
        """返回页面指定语言的修订列表（最新在前）。"""
        lang = validate_lang(lang)
        rows = self._conn.execute(
            f"SELECT id, page_id, lang, rev_no, title, summary, author_uid, created_at "
            f"FROM {self.REVISION_TABLE_NAME} WHERE page_id = ? AND lang = ? "
            f"ORDER BY rev_no DESC LIMIT ?",
            (page_id, lang, limit),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def list_contributors(self, page_id: int) -> list[dict[str, Any]]:
        """统计页面的历史贡献者：谁编写过、各编辑了多少次、首次/最近一次编辑时间。

        数据来源为 revisions 表（每次保存都会留下一条带 author_uid 的修订），
        跨语言汇总，按编辑次数降序返回。
        """
        rows = self._conn.execute(
            f"SELECT author_uid, COUNT(*) AS edit_count, "
            f"MIN(created_at) AS first_at, MAX(created_at) AS last_at "
            f"FROM {self.REVISION_TABLE_NAME} WHERE page_id = ? "
            f"GROUP BY author_uid ORDER BY edit_count DESC, last_at DESC",
            (page_id,),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_revision(self, rev_id: int) -> dict[str, Any] | None:
        """按 id 读取修订（含完整 title/content 快照与语言）；不存在返回 None。"""
        row = self._conn.execute(
            f"SELECT * FROM {self.REVISION_TABLE_NAME} WHERE id = ?", (rev_id,)
        ).fetchone()
        return self._row_to_dict(row)

    def restore_revision(self, page_id: int, rev_id: int, author_uid: int) -> dict[str, Any]:
        """把指定修订的内容恢复为该页面对应语言的新修订。

        :raises WikiPageNotFoundError / WikiRevisionNotFoundError
        """
        page = self.get_page_by_id(page_id)
        if page is None:
            raise WikiPageNotFoundError(f"页面 id={page_id} 不存在")
        revision = self.get_revision(rev_id)
        if revision is None or int(revision["page_id"]) != int(page_id):
            raise WikiRevisionNotFoundError(f"修订 id={rev_id} 不存在")
        lang = validate_lang(revision["lang"])
        summary = f"Restored to rev {revision['rev_no']}"
        return self._apply_update(page, revision["content"], lang, summary, author_uid)

    # ------------------------------------------------------------------
    # 键值接口（以 slug 为 key；仅保留只读语义）
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        page = self.get_page(key)
        return default if page is None else page

    def set(self, key: str, value: Any) -> None:
        raise NotImplementedError("pages 表不支持键值写入，请使用 create_page()/update_page()")

    def delete(self, key: str) -> bool:
        try:
            self.delete_page(key)
            return True
        except WikiPageNotFoundError:
            return False

    def keys(self) -> list[str]:
        rows = self._conn.execute(
            f"SELECT slug FROM {self.TABLE_NAME} ORDER BY slug"
        ).fetchall()
        return [row["slug"] for row in rows]
