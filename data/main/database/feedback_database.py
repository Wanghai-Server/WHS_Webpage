"""反馈数据库（基于 sqlite3）。

``feedback`` 表存储用户反馈（标题 + Markdown 正文 + 分类 + 状态），
``feedback_comments`` 表存储每条反馈下的评论（Markdown 正文）。

- 分类：``bug`` / ``suggestion`` / ``other``；
- 状态：``pending``（待处理）/ ``resolved``（已处理）/ ``closed``（已关闭）；
- 反馈与评论的作者均记录 ``author_uid``，展示时由 API 层解析为名称；
- 删除反馈时由应用层级联删除其全部评论。

数据库文件由 :class:`BasicDatabase` 统一规范化到 ``data/database/feedback.db``。
继承 :class:`UserDatabase` 复用其表管理 / 迁移 / 连接生命周期逻辑。
"""

import datetime
import re
from typing import Any

from .user_database import UserDatabase
from .text_utils import strip_mc_color_codes

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

FEEDBACK_TABLE_COLUMNS: dict[str, str] = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "title": "TEXT NOT NULL",                    # 标题（纯文本）
    "content": "TEXT NOT NULL",                  # Markdown 正文
    "category": "TEXT NOT NULL DEFAULT 'other'",  # bug / suggestion / other
    "status": "TEXT NOT NULL DEFAULT 'pending'",  # pending / resolved / closed
    "author_uid": "INTEGER NOT NULL",
    "created_at": "TEXT NOT NULL",               # ISO 8601
    "updated_at": "TEXT NOT NULL",               # 最近编辑时间（ISO 8601）
}

FEEDBACK_COMMENT_TABLE_COLUMNS: dict[str, str] = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "feedback_id": "INTEGER NOT NULL",
    "author_uid": "INTEGER NOT NULL",
    "content": "TEXT NOT NULL",                  # Markdown 正文
    "created_at": "TEXT NOT NULL",               # ISO 8601
}

FEEDBACK_CATEGORIES = ("bug", "suggestion", "other")
FEEDBACK_STATUSES = ("pending", "resolved", "closed")
DEFAULT_CATEGORY = "other"
DEFAULT_STATUS = "pending"

MAX_TITLE_LENGTH = 200
MAX_CONTENT_LENGTH = 100_000
MAX_COMMENT_LENGTH = 20_000

DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 50


class FeedbackDatabaseError(Exception):
    """反馈数据层错误：携带错误码（由后端统一翻译为结构化双语响应）。"""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _escape_like(text: str) -> str:
    """转义 LIKE 通配符，使搜索词按字面匹配。"""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _strip_markdown(text: str) -> str:
    """粗略剥离 Markdown 标记，用于列表摘要展示。"""
    text = strip_mc_color_codes(text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"[#>*_~|-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _make_excerpt(content: str, limit: int = 160) -> str:
    """生成列表摘要：剥离 Markdown 后截断。"""
    text = _strip_markdown(content)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


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


def _validate_category(category: str) -> str:
    if category not in FEEDBACK_CATEGORIES:
        raise FeedbackDatabaseError("feedback_category_invalid")
    return category


def _validate_status(status: str) -> str:
    if status not in FEEDBACK_STATUSES:
        raise FeedbackDatabaseError("feedback_status_invalid")
    return status


def _validate_title(title: str) -> str:
    title = (title or "").strip()
    if not title:
        raise FeedbackDatabaseError("feedback_title_empty")
    if len(title) > MAX_TITLE_LENGTH:
        raise FeedbackDatabaseError("feedback_title_too_large")
    return title


def _validate_content(content: str) -> str:
    content = (content or "").strip()
    if not content:
        raise FeedbackDatabaseError("feedback_content_empty")
    if len(content) > MAX_CONTENT_LENGTH:
        raise FeedbackDatabaseError("feedback_content_too_large")
    return content


def _validate_comment(content: str) -> str:
    content = (content or "").strip()
    if not content:
        raise FeedbackDatabaseError("feedback_comment_empty")
    if len(content) > MAX_COMMENT_LENGTH:
        raise FeedbackDatabaseError("feedback_comment_too_large")
    return content


class FeedbackDatabase(UserDatabase):
    """存储反馈与评论的 sqlite3 数据库（对应 ``feedback.db``）。"""

    TABLE_NAME = "feedback"
    TABLE_COLUMNS = FEEDBACK_TABLE_COLUMNS
    COMMENT_TABLE_NAME = "feedback_comments"
    COMMENT_TABLE_COLUMNS = FEEDBACK_COMMENT_TABLE_COLUMNS

    def __init__(self, database_path: str = "feedback.db") -> None:
        super().__init__(database_path)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """打开数据库，确保 feedback + feedback_comments 表存在。"""
        super().connect()
        self.create_table(
            self.COMMENT_TABLE_NAME, self.COMMENT_TABLE_COLUMNS, if_not_exists=True
        )

    # ------------------------------------------------------------------
    # 反馈
    # ------------------------------------------------------------------

    def create_feedback(self, title: str, content: str, category: str, author_uid: int) -> int:
        """创建一条反馈并返回自增 id。"""
        title = _validate_title(title)
        content = _validate_content(content)
        category = _validate_category((category or DEFAULT_CATEGORY).strip() or DEFAULT_CATEGORY)
        now = _now()
        cursor = self._conn.execute(
            f"INSERT INTO {self.TABLE_NAME} "
            f"(title, content, category, status, author_uid, created_at, updated_at) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, content, category, DEFAULT_STATUS, int(author_uid), now, now),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def get_feedback(self, feedback_id: int) -> dict[str, Any] | None:
        """按 id 读取反馈；不存在返回 None。"""
        row = self._conn.execute(
            f"SELECT * FROM {self.TABLE_NAME} WHERE id = ?", (int(feedback_id),)
        ).fetchone()
        return self._row_to_dict(row)

    def list_feedbacks(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        *,
        status: str = "",
        category: str = "",
        q: str = "",
    ) -> dict[str, Any]:
        """分页列出反馈（最新在前），支持状态 / 分类筛选与关键词搜索。

        返回 ``{"total", "page", "page_size", "items"}``；每项附带 ``excerpt``
        与 ``comment_count``。
        """
        page = max(1, int(page)) if page is not None else 1
        if page_size is None:
            page_size = DEFAULT_PAGE_SIZE
        page_size = min(max(1, int(page_size)), MAX_PAGE_SIZE)
        where: list[str] = []
        params: list[Any] = []
        if status:
            _validate_status(status)
            where.append("status = ?")
            params.append(status)
        if category:
            _validate_category(category)
            where.append("category = ?")
            params.append(category)
        q = (q or "").strip()[:100]
        if q:
            like = f"%{_escape_like(q)}%"
            where.append("(title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')")
            params.extend([like, like])
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        total = int(
            self._conn.execute(
                f"SELECT COUNT(*) AS n FROM {self.TABLE_NAME} {where_sql}", tuple(params)
            ).fetchone()["n"]
        )
        try:
            rows = self._conn.execute(
                f"SELECT * FROM {self.TABLE_NAME} {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
                tuple(params) + (page_size, (page - 1) * page_size),
            ).fetchall()
        except OverflowError:
            # page 过大时 (page-1)*page_size 超出 SQLite OFFSET 的 64 位整数范围，
            # 统一转为 400 结构化错误（feedback_page_invalid），不让其冒泡成 500。
            raise FeedbackDatabaseError("feedback_page_invalid") from None
        items = []
        for row in rows:
            item = self._row_to_dict(row)
            item["excerpt"] = _make_excerpt(item.get("content") or "")
            item["comment_count"] = self.comment_count(item["id"])
            items.append(item)
        return {"total": total, "page": page, "page_size": page_size, "items": items}

    def update_feedback(
        self, feedback_id: int, title: str, content: str, category: str
    ) -> bool:
        """更新反馈标题 / 正文 / 分类（状态与作者不变），返回是否更新成功。"""
        if self.get_feedback(feedback_id) is None:
            raise FeedbackDatabaseError("feedback_not_found")
        title = _validate_title(title)
        content = _validate_content(content)
        category = _validate_category((category or DEFAULT_CATEGORY).strip() or DEFAULT_CATEGORY)
        self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET title = ?, content = ?, category = ?, updated_at = ? "
            f"WHERE id = ?",
            (title, content, category, _now(), int(feedback_id)),
        )
        self._conn.commit()
        return True

    def delete_feedback(self, feedback_id: int) -> bool:
        """删除反馈及其全部评论，返回是否真的删除了。"""
        if self.get_feedback(feedback_id) is None:
            return False
        # 应用层级联：先删评论，再删反馈（DDL 无外键）
        self._conn.execute(
            f"DELETE FROM {self.COMMENT_TABLE_NAME} WHERE feedback_id = ?", (int(feedback_id),)
        )
        cursor = self._conn.execute(
            f"DELETE FROM {self.TABLE_NAME} WHERE id = ?", (int(feedback_id),)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def set_status(self, feedback_id: int, status: str) -> bool:
        """设置反馈状态（仅状态变化，不更新 updated_at 之外的内容）。"""
        status = _validate_status(status)
        if self.get_feedback(feedback_id) is None:
            raise FeedbackDatabaseError("feedback_not_found")
        cursor = self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now(), int(feedback_id)),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def search_feedbacks(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """全量搜索反馈（标题 / 正文），返回带摘要的结果列表。"""
        q = (query or "").strip()[:100]
        if not q:
            return []
        like = f"%{_escape_like(q)}%"
        rows = self._conn.execute(
            f"SELECT * FROM {self.TABLE_NAME} "
            f"WHERE title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\' "
            f"ORDER BY id DESC LIMIT ?",
            (like, like, int(limit)),
        ).fetchall()
        results = []
        for row in rows:
            item = self._row_to_dict(row)
            results.append(
                {
                    "id": item["id"],
                    "title": item["title"],
                    "category": item["category"],
                    "status": item["status"],
                    "author_uid": item["author_uid"],
                    "updated_at": item["updated_at"],
                    "snippet": _make_snippet(item.get("content") or "", q),
                }
            )
        return results

    # ------------------------------------------------------------------
    # 评论
    # ------------------------------------------------------------------

    def add_comment(self, feedback_id: int, author_uid: int, content: str) -> int:
        """为反馈添加一条评论并返回自增 id。"""
        if self.get_feedback(feedback_id) is None:
            raise FeedbackDatabaseError("feedback_not_found")
        content = _validate_comment(content)
        cursor = self._conn.execute(
            f"INSERT INTO {self.COMMENT_TABLE_NAME} (feedback_id, author_uid, content, created_at) "
            f"VALUES (?, ?, ?, ?)",
            (int(feedback_id), int(author_uid), content, _now()),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def get_comment(self, comment_id: int) -> dict[str, Any] | None:
        """按 id 读取评论；不存在返回 None。"""
        row = self._conn.execute(
            f"SELECT * FROM {self.COMMENT_TABLE_NAME} WHERE id = ?", (int(comment_id),)
        ).fetchone()
        return self._row_to_dict(row)

    def list_comments(self, feedback_id: int) -> list[dict[str, Any]]:
        """按时间正序返回某条反馈的全部评论。"""
        rows = self._conn.execute(
            f"SELECT * FROM {self.COMMENT_TABLE_NAME} WHERE feedback_id = ? ORDER BY id ASC",
            (int(feedback_id),),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def comment_count(self, feedback_id: int) -> int:
        """返回某条反馈的评论数。"""
        row = self._conn.execute(
            f"SELECT COUNT(*) AS n FROM {self.COMMENT_TABLE_NAME} WHERE feedback_id = ?",
            (int(feedback_id),),
        ).fetchone()
        return int(row["n"])

    # ------------------------------------------------------------------
    # 键值接口：以反馈 id（字符串形式）为 key（保持基类接口可用）
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        try:
            feedback = self.get_feedback(int(key))
        except (TypeError, ValueError):
            return default
        return default if feedback is None else feedback

    def set(self, key: str, value: Any) -> None:
        raise NotImplementedError("feedback 表不支持键值写入，请使用 create_feedback()")

    def delete(self, key: str) -> bool:
        try:
            return self.delete_feedback(int(key))
        except (TypeError, ValueError):
            return False

    def keys(self) -> list[str]:
        rows = self._conn.execute(
            f"SELECT id FROM {self.TABLE_NAME} ORDER BY id"
        ).fetchall()
        return [str(row["id"]) for row in rows]
