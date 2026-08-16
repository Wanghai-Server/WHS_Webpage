"""用户基础数据数据库（基于 sqlite3）。

数据库文件由 :class:`BasicDatabase` 统一规范化到
``data/database/basic_user_data.db``，内部使用一张 ``users`` 表存储用户基础数据。
"""

import re
import sqlite3
from typing import Any

from .basic_database import BasicDatabase

# 用户名仅允许：英文字母、数字、下划线，且至少一个字符。
USERNAME_PATTERN = re.compile(r"[a-zA-Z0-9_]+")

# 邮箱仅允许：英文字母、数字、下划线、@、点号和短横杆，且至少一个字符。
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_@.-]+")

# 密码仅允许 ASCII 字符（不允许出现非 ASCII 字符）。
PASSWORD_PATTERN = re.compile(r"^[\x00-\x7f]+$")

# 合法的 SQL 标识符（表名 / 列名）。
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# 表结构：列名 -> 列定义（已修正为 SQLite 标准类型）。
USER_TABLE_COLUMNS: dict[str, str] = {
    "uid": "INTEGER PRIMARY KEY AUTOINCREMENT",   # 自增且永不重复
    "email": "TEXT NOT NULL UNIQUE",               # 唯一，满足 [a-zA-Z0-9_@.-]+
    "username": "TEXT NOT NULL UNIQUE",            # 唯一，满足 [a-zA-Z0-9_]+
    "fullname": "TEXT NOT NULL",                   # 任意值，反斜杠按字面保存
    "password": "TEXT NOT NULL",                   # 后端计算的 sha256 哈希
    "avatar": "TEXT",                               # 头像文件名，可空（NULL 表示无头像）
}


class UserDatabaseError(Exception):
    """用户数据库相关错误的基类，携带稳定的错误码 ``code``。"""

    code = "user_database_error"


class UsernameInvalidError(UserDatabaseError):
    """用户名不满足 ``[a-zA-Z0-9_]+`` 要求。"""

    code = "username_invalid"


class EmailInvalidError(UserDatabaseError):
    """邮箱不满足 ``[a-zA-Z0-9_@.-]+`` 要求。"""

    code = "email_invalid"


class PasswordInvalidError(UserDatabaseError):
    """密码包含非 ASCII 字符。"""

    code = "password_invalid"


class UsernameExistsError(UserDatabaseError):
    """用户名已存在。"""

    code = "username_exists"


class EmailExistsError(UserDatabaseError):
    """邮箱已存在。"""

    code = "email_exists"


class UserNotFoundError(UserDatabaseError):
    """指定用户不存在。"""

    code = "user_not_found"


# 错误码 -> 双语消息（与前端 title_suffix 的 zh/en 结构保持一致）。
ERROR_MESSAGES: dict[str, dict[str, str]] = {
    "username_invalid": {
        "zh": "用户名仅允许英文字母、数字和下划线",
        "en": "Username may only contain letters, digits and underscores",
    },
    "email_invalid": {
        "zh": "邮箱格式不合法",
        "en": "Invalid email format",
    },
    "password_invalid": {
        "zh": "密码格式错误",
        "en": "Invalid password format",
    },
    "username_exists": {
        "zh": "用户名已被使用",
        "en": "Username already taken",
    },
    "email_exists": {
        "zh": "邮箱已被注册",
        "en": "Email already registered",
    },
    "user_not_found": {
        "zh": "用户不存在",
        "en": "User not found",
    },
}


class UserDatabase(BasicDatabase):
    """存储用户基础数据的 sqlite3 数据库。

    对应数据库文件 ``basic_user_data.db``，内部表 ``users``：

    =========  ================================  =============================
    键         修正后的 SQLite 类型               说明
    =========  ================================  =============================
    uid        INTEGER PRIMARY KEY AUTOINCREMENT  自增且永不重复
    email      TEXT NOT NULL UNIQUE               唯一，满足 [a-zA-Z0-9_@.-]+
    username   TEXT NOT NULL UNIQUE               唯一，满足 [a-zA-Z0-9_]+
    fullname   TEXT NOT NULL                      任意值，反斜杠按字面保存
    password   TEXT NOT NULL                      后端计算的 sha256 哈希
    avatar     TEXT                               头像文件名，可空（NULL 表示无头像）
    =========  ================================  =============================
    """

    TABLE_NAME = "users"

    def __init__(self, database_path: str = "basic_user_data.db") -> None:
        super().__init__(database_path)
        self._connection: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """打开数据库并确保 ``users`` 表存在。"""
        super().connect()
        self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self.create_table(self.TABLE_NAME, USER_TABLE_COLUMNS, if_not_exists=True)
        self._migrate()

    def close(self) -> None:
        """提交并关闭连接。"""
        if self._connection is not None:
            self._connection.commit()
            self._connection.close()
        super().close()

    def _migrate(self) -> None:
        """为已存在的旧表补充缺失的列（向后兼容）。"""
        existing_cols = {
            row["name"]
            for row in self._conn.execute(
                f"PRAGMA table_info({self.TABLE_NAME})"
            ).fetchall()
        }
        for name, definition in USER_TABLE_COLUMNS.items():
            if name not in existing_cols:
                self._conn.execute(
                    f"ALTER TABLE {self.TABLE_NAME} ADD COLUMN {name} {definition}"
                )
        self._conn.commit()

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @property
    def _conn(self) -> sqlite3.Connection:
        """返回当前连接；未连接时抛出异常。"""
        if self._connection is None or not self._connected:
            raise RuntimeError("数据库尚未连接，请先调用 connect()")
        return self._connection

    @staticmethod
    def _validate_username(username: str) -> str:
        """校验用户名；不合法时抛出 :class:`UsernameInvalidError`。"""
        if not isinstance(username, str) or USERNAME_PATTERN.fullmatch(username) is None:
            raise UsernameInvalidError(
                f"用户名 {username!r} 不合法：仅允许英文字母、数字和下划线（至少一个字符）"
            )
        return username

    @staticmethod
    def _validate_email(email: str) -> str:
        """校验邮箱；不合法时抛出 :class:`EmailInvalidError`。"""
        if not isinstance(email, str) or EMAIL_PATTERN.fullmatch(email) is None:
            raise EmailInvalidError(
                f"邮箱 {email!r} 不合法：仅允许英文字母、数字、下划线、@、点号和短横杆（至少一个字符）"
            )
        return email

    @staticmethod
    def _validate_password(password: str) -> str:
        """校验密码；包含非 ASCII 字符时抛出 :class:`PasswordInvalidError`。"""
        if not isinstance(password, str) or PASSWORD_PATTERN.fullmatch(password) is None:
            raise PasswordInvalidError("密码不允许包含非 ASCII 字符")
        return password

    @staticmethod
    def _validate_identifier(name: str) -> str:
        """校验表名 / 列名，防止 SQL 注入。"""
        if not isinstance(name, str) or _IDENTIFIER_PATTERN.fullmatch(name) is None:
            raise ValueError(f"非法的 SQL 标识符：{name!r}")
        return name

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {key: row[key] for key in row.keys()}

    # ------------------------------------------------------------------
    # 数据表管理（BasicDatabase 抽象方法）
    # ------------------------------------------------------------------

    def create_table(
        self,
        table_name: str,
        columns: dict[str, str] | None = None,
        *,
        if_not_exists: bool = True,
    ) -> None:
        """创建数据表。

        ``columns`` 为「列名 -> 列定义」映射，列定义是原样拼入 SQL 的
        SQLite 类型 / 约束片段（例如 ``"INTEGER PRIMARY KEY AUTOINCREMENT"``）。
        """
        if not columns:
            raise ValueError("创建表需要提供列定义")
        table_name = self._validate_identifier(table_name)
        definitions = []
        for name, definition in columns.items():
            self._validate_identifier(name)
            definitions.append(f"{name} {definition}")
        clause = "IF NOT EXISTS" if if_not_exists else ""
        self._conn.execute(
            f"CREATE TABLE {clause} {table_name} ({', '.join(definitions)})"
        )
        self._conn.commit()

    def drop_table(self, table_name: str, *, if_exists: bool = False) -> None:
        """删除数据表。"""
        table_name = self._validate_identifier(table_name)
        clause = "IF EXISTS" if if_exists else ""
        self._conn.execute(f"DROP TABLE {clause} {table_name}")
        self._conn.commit()

    def list_tables(self) -> list[str]:
        """返回当前数据库中所有数据表的名称列表。"""
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [row["name"] for row in rows]

    # ------------------------------------------------------------------
    # 用户业务方法
    # ------------------------------------------------------------------

    def create_user(self, username: str, email: str, fullname: str, password: str) -> int:
        """创建用户并返回自增的 ``uid``。

        ``email`` 需满足 ``[a-zA-Z0-9_@.-]+``，重复时抛出 :class:`EmailExistsError`。
        ``password`` 应为后端已经计算好的 sha256 哈希字符串，本方法原样存储、不做哈希。
        """
        username = self._validate_username(username)
        email = self._validate_email(email)
        password = self._validate_password(password)
        if self.get_user(username=username) is not None:
            raise UsernameExistsError(f"用户名 {username!r} 已存在")
        if self.get_user(email=email) is not None:
            raise EmailExistsError(f"邮箱 {email!r} 已存在")
        try:
            cursor = self._conn.execute(
                f"INSERT INTO {self.TABLE_NAME} (email, username, fullname, password) VALUES (?, ?, ?, ?)",
                (email, username, fullname, password),
            )
        except sqlite3.IntegrityError as exc:
            if "email" in str(exc):
                raise EmailExistsError(f"邮箱 {email!r} 已存在") from exc
            raise UsernameExistsError(f"用户名 {username!r} 已存在") from exc
        self._conn.commit()
        return int(cursor.lastrowid)

    def get_user(
        self,
        *,
        uid: int | None = None,
        username: str | None = None,
        email: str | None = None,
    ) -> dict[str, Any] | None:
        """按 ``uid`` / ``username`` / ``email`` 查询用户；不存在返回 ``None``。"""
        if uid is not None:
            row = self._conn.execute(
                f"SELECT * FROM {self.TABLE_NAME} WHERE uid = ?", (uid,)
            ).fetchone()
        elif username is not None:
            row = self._conn.execute(
                f"SELECT * FROM {self.TABLE_NAME} WHERE username = ?", (username,)
            ).fetchone()
        elif email is not None:
            row = self._conn.execute(
                f"SELECT * FROM {self.TABLE_NAME} WHERE email = ?", (email,)
            ).fetchone()
        else:
            raise ValueError("get_user 需要提供 uid、username 或 email 之一")
        return self._row_to_dict(row)

    def update_user(
        self,
        uid: int,
        *,
        email: str | None = None,
        fullname: str | None = None,
        password: str | None = None,
        avatar: str | None = None,
    ) -> None:
        """更新指定用户的 ``email`` / ``fullname`` / ``password`` / ``avatar``（未提供字段保持不变）。"""
        assignments: list[str] = []
        values: list[Any] = []
        if email is not None:
            email = self._validate_email(email)
            assignments.append("email = ?")
            values.append(email)
        if fullname is not None:
            assignments.append("fullname = ?")
            values.append(fullname)
        if password is not None:
            password = self._validate_password(password)
            assignments.append("password = ?")
            values.append(password)
        if avatar is not None:
            assignments.append("avatar = ?")
            values.append(avatar)
        if not assignments:
            return
        if self.get_user(uid=uid) is None:
            raise UserNotFoundError(f"uid={uid} 的用户不存在")
        if email is not None:
            other = self.get_user(email=email)
            if other is not None and other["uid"] != uid:
                raise EmailExistsError(f"邮箱 {email!r} 已存在")
        values.append(uid)
        self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET {', '.join(assignments)} WHERE uid = ?",
            values,
        )
        self._conn.commit()

    def delete_user(self, uid: int) -> bool:
        """按 ``uid`` 删除用户，返回是否真的删除了。"""
        cursor = self._conn.execute(
            f"DELETE FROM {self.TABLE_NAME} WHERE uid = ?", (uid,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def list_users(self) -> list[dict[str, Any]]:
        """返回所有用户（按 ``uid`` 升序）。"""
        rows = self._conn.execute(
            f"SELECT * FROM {self.TABLE_NAME} ORDER BY uid"
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    # ------------------------------------------------------------------
    # 键值接口（BasicDatabase 抽象方法，key 即 username）
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """以 ``username`` 为 key 读取用户，不存在时返回 ``default``。"""
        user = self.get_user(username=key)
        return default if user is None else user

    def set(self, key: str, value: Any) -> None:
        """以 ``username`` 为 key 写入 / 更新用户。

        ``value`` 需为字典，可包含 ``email``、``fullname``、``password``；
        用户已存在则更新，否则新建（新建时 email 必填，fullname/password 缺失按空字符串处理）。
        """
        username = self._validate_username(key)
        if not isinstance(value, dict):
            raise TypeError("value 必须是包含 email / fullname / password 的字典")
        existing = self.get_user(username=username)
        if existing is None:
            email = value.get("email")
            fullname = value.get("fullname")
            password = value.get("password")
            self.create_user(
                username,
                email if email is not None else "",
                fullname if fullname is not None else "",
                password if password is not None else "",
            )
        else:
            self.update_user(
                existing["uid"],
                email=value.get("email"),
                fullname=value.get("fullname"),
                password=value.get("password"),
            )

    def delete(self, key: str) -> bool:
        """以 ``username`` 为 key 删除用户，返回是否真的删除了。"""
        user = self.get_user(username=key)
        if user is None:
            return False
        return self.delete_user(user["uid"])

    def keys(self) -> list[str]:
        """返回所有 username 的列表（按 uid 升序）。"""
        rows = self._conn.execute(
            f"SELECT username FROM {self.TABLE_NAME} ORDER BY uid"
        ).fetchall()
        return [row["username"] for row in rows]