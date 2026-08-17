"""消息数据库（基于 sqlite3）。

``messages`` 表存储系统消息（``scope='system'``，所有人可见），
并预留定向消息（``scope='user'`` + ``target_uid``，未来功能）能力。

继承 :class:`UserDatabase` 复用其表管理 / 迁移 / 连接生命周期逻辑
（``connect`` / ``_migrate`` 均按子类的 ``TABLE_NAME`` / ``TABLE_COLUMNS`` 工作），
仅覆盖键值接口为消息语义。

数据库文件统一由 :class:`BasicDatabase` 规范化到 ``data/database/basic_message_data.db``。
"""

import datetime
import json
from typing import Any

from .user_database import UserDatabase

MESSAGE_TABLE_COLUMNS: dict[str, str] = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "scope": "TEXT NOT NULL",          # 'system'：系统消息（所有人可见）；'user'：定向消息（未来）
    "target_uid": "INTEGER",           # 定向消息的目标用户 uid；系统消息为 NULL
    "title": "TEXT NOT NULL DEFAULT ''",  # 消息标题（纯文本，列表展示用）
    "content": "TEXT NOT NULL",        # Markdown 内容
    "author_uid": "INTEGER NOT NULL",  # 发布者 uid
    "read_uids": "TEXT",               # JSON 数组：已读该消息的用户 uid 列表
    "created_at": "TEXT NOT NULL",     # ISO 8601 时间字符串
}


class MessageDatabase(UserDatabase):
    """存储系统/定向消息的 sqlite3 数据库。"""

    TABLE_NAME = "messages"
    TABLE_COLUMNS = MESSAGE_TABLE_COLUMNS

    def __init__(self, database_path: str = "basic_message_data.db") -> None:
        super().__init__(database_path)

    # ------------------------------------------------------------------
    # 消息业务方法
    # ------------------------------------------------------------------

    def create_message(
        self,
        title: str,
        content: str,
        author_uid: int,
        *,
        scope: str = "system",
        target_uid: int | None = None,
    ) -> int:
        """创建一条消息并返回自增 ``id``。"""
        if scope not in ("system", "user"):
            raise ValueError(f"非法的 scope: {scope!r}")
        if scope == "user" and target_uid is None:
            raise ValueError("定向消息必须指定 target_uid")
        created_at = datetime.datetime.now().isoformat(timespec="seconds")
        cursor = self._conn.execute(
            f"INSERT INTO {self.TABLE_NAME} (scope, target_uid, title, content, author_uid, created_at) "
            f"VALUES (?, ?, ?, ?, ?, ?)",
            (scope, target_uid, title, content, author_uid, created_at),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def get_message(self, message_id: int) -> dict[str, Any] | None:
        """按 id 读取消息；不存在返回 None。"""
        row = self._conn.execute(
            f"SELECT * FROM {self.TABLE_NAME} WHERE id = ?", (message_id,)
        ).fetchone()
        return self._row_to_dict(row)

    def list_system_messages(self, limit: int = 50) -> list[dict[str, Any]]:
        """返回系统消息列表（最新在前）。"""
        rows = self._conn.execute(
            f"SELECT * FROM {self.TABLE_NAME} WHERE scope = 'system' ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def list_user_messages(self, target_uid: int, limit: int = 50) -> list[dict[str, Any]]:
        """返回定向给指定用户的消息（未来功能）。"""
        rows = self._conn.execute(
            f"SELECT * FROM {self.TABLE_NAME} WHERE scope = 'user' AND target_uid = ? "
            f"ORDER BY id DESC LIMIT ?",
            (target_uid, limit),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def delete_message(self, message_id: int) -> bool:
        """按 id 删除消息，返回是否真的删除了。"""
        cursor = self._conn.execute(
            f"DELETE FROM {self.TABLE_NAME} WHERE id = ?", (message_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # 已读状态
    # ------------------------------------------------------------------

    @staticmethod
    def _json_to_uid_list(raw: Any) -> list[int]:
        """把 read_uids 的 JSON 文本解析成 uid 列表；空/非法返回 []。"""
        if not raw:
            return []
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        result: list[int] = []
        for item in data:
            try:
                result.append(int(item))
            except (TypeError, ValueError):
                continue
        return result

    @staticmethod
    def _uid_list_to_json(uids: list[int]) -> str:
        """把 uid 列表序列化为 JSON 文本（去重、升序）。"""
        return json.dumps(sorted({int(u) for u in uids}))

    def get_read_uids(self, message_id: int) -> list[int]:
        """返回已读该消息的用户 uid 列表。"""
        row = self.get_message(message_id)
        return self._json_to_uid_list(row["read_uids"]) if row else []

    def is_read_by(self, message_id: int, uid: int) -> bool:
        """判断指定用户是否已读该消息。"""
        return uid in self.get_read_uids(message_id)

    def add_read_user(self, message_id: int, uid: int) -> bool:
        """把 uid 加入消息的已读列表（幂等），返回是否真的发生了变更。"""
        if self.get_message(message_id) is None:
            return False
        uids = self.get_read_uids(message_id)
        if uid in uids:
            return False
        uids.append(uid)
        self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET read_uids = ? WHERE id = ?",
            (self._uid_list_to_json(uids), message_id),
        )
        self._conn.commit()
        return True

    # ------------------------------------------------------------------
    # 键值接口：以消息 id（字符串形式）为 key
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        try:
            msg = self.get_message(int(key))
        except (TypeError, ValueError):
            return default
        return default if msg is None else msg

    def set(self, key: str, value: Any) -> None:
        raise NotImplementedError("messages 表不支持键值写入，请使用 create_message()")

    def delete(self, key: str) -> bool:
        try:
            return self.delete_message(int(key))
        except (TypeError, ValueError):
            return False

    def keys(self) -> list[str]:
        rows = self._conn.execute(
            f"SELECT id FROM {self.TABLE_NAME} ORDER BY id"
        ).fetchall()
        return [str(row["id"]) for row in rows]
