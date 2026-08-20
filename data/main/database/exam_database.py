"""考试答题数据库（基于 sqlite3）。

``exam_answers`` 表按 (uid, question_id) 唯一存储每位玩家的答题记录，
用于"每答一题、锁存一题"：答案（JSON）、上传附件、该题得分与作答时间。

继承 :class:`UserDatabase` 复用其表管理 / 迁移 / 连接生命周期逻辑。

数据库文件统一由 :class:`BasicDatabase` 规范化到 ``data/database/exam_data.db``。
"""

import datetime
import json
from typing import Any

from .user_database import UserDatabase

EXAM_ANSWER_TABLE_COLUMNS: dict[str, str] = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "uid": "INTEGER NOT NULL",            # 答题玩家 uid
    "question_id": "INTEGER NOT NULL",    # 题目 id（对应 exam.yml questions 键）
    "answer": "TEXT",                     # JSON 序列化的答案（字符串或数组）
    "attachment": "TEXT",                 # 上传附件文件名（可选）
    "obtained_score": "INTEGER NOT NULL DEFAULT 0",  # 该题得分（主观题恒 0，管理员可改）
    "answered_at": "TEXT NOT NULL",       # ISO 8601 作答时间
}

# 考生信息表：开始答题前填写的个人信息 + 答题次数 / 是否及格。
# 注意：旧版曾含 qq_name / qq_number 两列（已废弃），由 connect() 迁移时彻底删除。
EXAM_PROFILE_TABLE_COLUMNS: dict[str, str] = {
    "uid": "INTEGER PRIMARY KEY",
    "player_name": "TEXT NOT NULL DEFAULT ''",  # 游戏名称（及格后注入 user_info）
    "is_premium": "TEXT NOT NULL DEFAULT 'offline'",  # 正版状态："premium" / "offline"
    "attempts": "INTEGER NOT NULL DEFAULT 0",   # 已完成答卷次数（上限 2）
    "passed": "INTEGER NOT NULL DEFAULT 0",     # 是否已及格（1/0）
    "review_requested": "INTEGER NOT NULL DEFAULT 0",  # 本答卷周期是否已申请重审（1/0）
    "updated_at": "TEXT NOT NULL DEFAULT ''",
}


class ExamDatabase(UserDatabase):
    """存储考试答题记录的 sqlite3 数据库。"""

    TABLE_NAME = "exam_answers"
    TABLE_COLUMNS = EXAM_ANSWER_TABLE_COLUMNS

    def __init__(self, database_path: str = "exam_data.db") -> None:
        super().__init__(database_path)

    def connect(self) -> None:
        """打开数据库、建表/迁移，并确保 (uid, question_id) 唯一。"""
        super().connect()
        self._conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_uid_qid "
            f"ON {self.TABLE_NAME}(uid, question_id)"
        )
        # 考生信息表：建表 + 迁移
        self.create_table("exam_profiles", EXAM_PROFILE_TABLE_COLUMNS, if_not_exists=True)
        existing = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(exam_profiles)").fetchall()
        }
        for name, definition in EXAM_PROFILE_TABLE_COLUMNS.items():
            if name not in existing:
                self._conn.execute(
                    f"ALTER TABLE exam_profiles ADD COLUMN {name} {definition}"
                )
        # 彻底删除已废弃的 QQ 字段列（旧版 exam_profiles 曾包含；SQLite >= 3.35 支持 DROP COLUMN）
        for legacy_col in ("qq_name", "qq_number"):
            if legacy_col in existing:
                try:
                    self._conn.execute(
                        f"ALTER TABLE exam_profiles DROP COLUMN {legacy_col}"
                    )
                    print(f"[exam-db] 已删除废弃列 {legacy_col}", flush=True)
                except Exception as exc:
                    print(f"[exam-db] 删除列 {legacy_col} 失败: {exc}", flush=True)
        self._conn.commit()

    # ------------------------------------------------------------------
    # 答题记录
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_answer(answer: Any) -> str:
        return json.dumps(answer, ensure_ascii=False)

    @staticmethod
    def _deserialize_answer(raw: str | None) -> Any:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return raw

    # 附件：统一以 JSON 字符串数组存储；兼容旧数据（单个文件名）。
    @staticmethod
    def _serialize_attachments(attachments: Any) -> str | None:
        if not attachments:
            return None
        if isinstance(attachments, str):
            attachments = [attachments]
        return json.dumps([str(a) for a in attachments if a], ensure_ascii=False)

    @staticmethod
    def _deserialize_attachments(raw: Any) -> list[str]:
        """把 attachment 字段解析为文件名列表；空/非法返回 []。"""
        if not raw:
            return []
        if isinstance(raw, list):
            return [str(x) for x in raw if x]
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except (TypeError, ValueError):
                return [raw]  # 旧格式：裸文件名
            if isinstance(data, list):
                return [str(x) for x in data if x]
            if isinstance(data, str) and data:
                return [data]  # 旧格式：JSON 包裹的单个文件名
        return []

    def save_answer(
        self,
        uid: int,
        question_id: int,
        answer: Any,
        obtained_score: int = 0,
        attachment: Any = None,
    ) -> None:
        """插入或更新 (uid, question_id) 的答题记录（幂等 upsert）。

        ``attachment`` 为文件名列表（也可传单个文件名，自动包装为列表）。
        """
        answered_at = datetime.datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            f"INSERT INTO {self.TABLE_NAME} "
            f"(uid, question_id, answer, attachment, obtained_score, answered_at) "
            f"VALUES (?, ?, ?, ?, ?, ?) "
            f"ON CONFLICT(uid, question_id) DO UPDATE SET "
            f"answer=excluded.answer, "
            f"attachment=excluded.attachment, "
            f"obtained_score=excluded.obtained_score, "
            f"answered_at=excluded.answered_at",
            (uid, question_id, self._serialize_answer(answer),
             self._serialize_attachments(attachment),
             int(obtained_score), answered_at),
        )
        self._conn.commit()

    def get_answer(self, uid: int, question_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            f"SELECT * FROM {self.TABLE_NAME} WHERE uid = ? AND question_id = ?",
            (uid, question_id),
        ).fetchone()
        if row is None:
            return None
        item = self._row_to_dict(row)
        item["answer"] = self._deserialize_answer(item.get("answer"))
        item["attachment"] = self._deserialize_attachments(item.get("attachment"))
        return item

    def get_answers(self, uid: int) -> dict[int, dict[str, Any]]:
        """返回该用户全部答题记录：question_id -> {answer, attachment, obtained_score, answered_at}。"""
        rows = self._conn.execute(
            f"SELECT * FROM {self.TABLE_NAME} WHERE uid = ? ORDER BY question_id",
            (uid,),
        ).fetchall()
        result: dict[int, dict[str, Any]] = {}
        for row in rows:
            item = self._row_to_dict(row)
            item["answer"] = self._deserialize_answer(item.get("answer"))
            item["attachment"] = self._deserialize_attachments(item.get("attachment"))
            result[int(item["question_id"])] = item
        return result

    def delete_answer(self, uid: int, question_id: int) -> bool:
        cursor = self._conn.execute(
            f"DELETE FROM {self.TABLE_NAME} WHERE uid = ? AND question_id = ?",
            (uid, question_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def delete_answers(self, uid: int) -> bool:
        """清空某用户的全部答题记录，返回是否删除了行。"""
        cursor = self._conn.execute(
            f"DELETE FROM {self.TABLE_NAME} WHERE uid = ?", (uid,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def remove_attachment(self, uid: int, question_id: int, filename: str) -> bool:
        """从某条答题记录的附件列表中移除指定文件，返回是否真的移除了。"""
        rec = self.get_answer(uid, question_id)
        if rec is None:
            return False
        atts = rec.get("attachment") or []
        if filename not in atts:
            return False
        remaining = [a for a in atts if a != filename]
        self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET attachment = ? WHERE uid = ? AND question_id = ?",
            (self._serialize_attachments(remaining), uid, question_id),
        )
        self._conn.commit()
        return True

    def reset_candidate(self, uid: int) -> None:
        """重置考生：清空答题记录，并清零完成次数、及格标记与重审申请（允许重新答题）。"""
        self.delete_answers(uid)
        profile = self.get_profile(uid)
        if profile is not None:
            self._conn.execute(
                "UPDATE exam_profiles SET attempts = 0, passed = 0, review_requested = 0, updated_at = ? WHERE uid = ?",
                (datetime.datetime.now().isoformat(timespec="seconds"), uid),
            )
            self._conn.commit()

    def set_score(self, uid: int, question_id: int, score: int) -> None:
        """仅更新某题实际得分（管理员改分用，不触碰答案/附件）。"""
        self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET obtained_score = ? WHERE uid = ? AND question_id = ?",
            (int(score), uid, question_id),
        )
        self._conn.commit()

    def list_answered_uids(self) -> list[int]:
        """返回有答题记录的用户 uid 列表（升序）。"""
        rows = self._conn.execute(
            f"SELECT DISTINCT uid FROM {self.TABLE_NAME} ORDER BY uid"
        ).fetchall()
        return [row["uid"] for row in rows]

    # ------------------------------------------------------------------
    # 考生信息 / 次数 / 及格
    # ------------------------------------------------------------------

    def get_profile(self, uid: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM exam_profiles WHERE uid = ?", (uid,)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def save_profile(self, uid: int, player_name: str, is_premium: str) -> None:
        updated_at = datetime.datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            "INSERT INTO exam_profiles (uid, player_name, is_premium, attempts, passed, updated_at) "
            "VALUES (?, ?, ?, 0, 0, ?) "
            "ON CONFLICT(uid) DO UPDATE SET "
            "player_name=excluded.player_name, "
            "is_premium=excluded.is_premium, "
            "updated_at=excluded.updated_at",
            (uid, player_name, is_premium, updated_at),
        )
        self._conn.commit()

    def increment_attempts(self, uid: int) -> int:
        """已完成答卷次数 +1，返回新值。"""
        profile = self.get_profile(uid)
        if profile is None:
            self.save_profile(uid, "", "offline")
            attempts = 0
        else:
            attempts = int(profile.get("attempts", 0))
        attempts += 1
        self._conn.execute(
            "UPDATE exam_profiles SET attempts = ?, updated_at = ? WHERE uid = ?",
            (attempts, datetime.datetime.now().isoformat(timespec="seconds"), uid),
        )
        self._conn.commit()
        return attempts

    def mark_passed(self, uid: int) -> None:
        profile = self.get_profile(uid)
        if profile is None:
            self.save_profile(uid, "", "offline")
        self._conn.execute(
            "UPDATE exam_profiles SET passed = 1, updated_at = ? WHERE uid = ?",
            (datetime.datetime.now().isoformat(timespec="seconds"), uid),
        )
        self._conn.commit()

    def can_answer(self, uid: int) -> bool:
        """是否允许答题：次数 < 2 且未及格。"""
        profile = self.get_profile(uid)
        if profile is None:
            return True
        return int(profile.get("attempts", 0)) < 2 and not bool(profile.get("passed"))

    # ------------------------------------------------------------------
    # 重审申请（防连点：本答卷周期内最多申请一次，重做后重置）
    # ------------------------------------------------------------------

    def is_review_requested(self, uid: int) -> bool:
        """本答卷周期是否已申请过重审。"""
        profile = self.get_profile(uid)
        return bool(profile and profile.get("review_requested"))

    def set_review_requested(self, uid: int, value: bool) -> None:
        """设置本答卷周期的重审申请标记（True 已申请 / False 清除）。"""
        profile = self.get_profile(uid)
        if profile is None:
            self.save_profile(uid, "", "", "")
        self._conn.execute(
            "UPDATE exam_profiles SET review_requested = ?, updated_at = ? WHERE uid = ?",
            (1 if value else 0, datetime.datetime.now().isoformat(timespec="seconds"), uid),
        )
        self._conn.commit()
