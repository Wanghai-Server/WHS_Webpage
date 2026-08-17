"""用户基础数据数据库（基于 sqlite3）。

数据库文件由 :class:`BasicDatabase` 统一规范化到
``data/database/basic_user_data.db``，内部使用一张 ``users`` 表存储用户基础数据。
"""

import json
import re
import sqlite3
from typing import Any

from .basic_database import BasicDatabase

# 用户名仅允许：英文字母、数字、下划线，且至少一个字符。
USERNAME_PATTERN = re.compile(r"[a-zA-Z0-9_]+")

# 玩家名称（Minecraft 名称）仅允许：英文字母、数字、下划线，且至少一个字符。
PLAYER_NAME_PATTERN = re.compile(r"[a-zA-Z0-9_]+")

# 三段式邮箱：本地部分(字母/数字/_/./-)+ 单个@ + 域名(至少一个点)。
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+")

# 密码仅允许 ASCII 字符（不允许出现非 ASCII 字符）。
PASSWORD_PATTERN = re.compile(r"^[\x00-\x7f]+$")

# 合法的 SQL 标识符（表名 / 列名）。
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# 表结构：列名 -> 列定义（已修正为 SQLite 标准类型）。
USER_TABLE_COLUMNS: dict[str, str] = {
    "uid": "INTEGER PRIMARY KEY AUTOINCREMENT",   # 自增且永不重复
    "email": "TEXT NOT NULL UNIQUE",               # 唯一，满足 [a-zA-Z0-9_@.-]+
    "username": "TEXT NOT NULL UNIQUE",            # 唯一，满足 [a-zA-Z0-9_]+
    "fullname": "TEXT",                            # 昵称，可空；注册时不自动注入，之后在用户设置里填
    "password": "TEXT NOT NULL",                   # 后端计算的 sha256 哈希
    "avatar": "TEXT",                               # 头像文件名，可空（NULL 表示无头像）
    "permission": "INTEGER NOT NULL DEFAULT 1",     # 0=guest 1=user 2=player 3=admin 4=owner
    "locked": "INTEGER NOT NULL DEFAULT 0",         # 0/1，连续输错 5 次后锁定
    "banned": "INTEGER NOT NULL DEFAULT 0",         # 0/1，管理员封禁
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


class PlayerNameExistsError(UserDatabaseError):
    """玩家名称（Minecraft 名称）已被占用。"""

    code = "player_name_exists"


class UserNotFoundError(UserDatabaseError):
    """指定用户不存在。"""

    code = "user_not_found"


# 错误码 -> 双语消息（与前端 title_suffix 的 zh/en 结构保持一致）。
ERROR_MESSAGES: dict[str, dict[str, str]] = {
    "username_invalid": {
        "zh": "用户名仅允许英文字母、数字和下划线",
        "en": "Username may only contain letters, digits and underscores",
    },
    "player_name_invalid": {
        "zh": "玩家名仅允许英文字母、数字和下划线",
        "en": "Player name may only contain letters, digits and underscores",
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
    "player_name_exists": {
        "zh": "该玩家名已被占用",
        "en": "Player name already taken",
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
    TABLE_COLUMNS = USER_TABLE_COLUMNS

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
        self.create_table(self.TABLE_NAME, self.TABLE_COLUMNS, if_not_exists=True)
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
        for name, definition in self.TABLE_COLUMNS.items():
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

    def create_user(self, username: str, email: str, fullname: str = "", password: str = "") -> int:
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

    def set_permission(self, uid: int, permission: int) -> None:
        """设置用户的权限等级（0~4）。"""
        if not isinstance(permission, int) or isinstance(permission, bool) or not (0 <= permission <= 4):
            raise ValueError(f"非法的 permission 值: {permission!r}")
        if self.get_user(uid=uid) is None:
            raise UserNotFoundError(f"uid={uid} 的用户不存在")
        self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET permission = ? WHERE uid = ?",
            (permission, uid),
        )
        self._conn.commit()

    def set_locked(self, uid: int, locked: bool) -> None:
        """设置用户的锁定状态（True/False）。"""
        if self.get_user(uid=uid) is None:
            raise UserNotFoundError(f"uid={uid} 的用户不存在")
        self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET locked = ? WHERE uid = ?",
            (1 if locked else 0, uid),
        )
        self._conn.commit()

    def set_username(self, uid: int, username: str) -> None:
        """更新用户名（校验格式 + 唯一性）。"""
        username = self._validate_username(username)
        if self.get_user(uid=uid) is None:
            raise UserNotFoundError(f"uid={uid} 的用户不存在")
        other = self.get_user(username=username)
        if other is not None and other["uid"] != uid:
            raise UsernameExistsError(f"用户名 {username!r} 已存在")
        self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET username = ? WHERE uid = ?",
            (username, uid),
        )
        self._conn.commit()

    def set_banned(self, uid: int, banned: bool) -> None:
        """设置用户的封禁状态（True/False）。"""
        if self.get_user(uid=uid) is None:
            raise UserNotFoundError(f"uid={uid} 的用户不存在")
        self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET banned = ? WHERE uid = ?",
            (1 if banned else 0, uid),
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


# 用户信息表结构：uid 与 users 表一致（非自增），其余字段可空（NULL 表示“不透露”）。
USER_INFO_TABLE_COLUMNS: dict[str, str] = {
    "uid": "INTEGER PRIMARY KEY",  # 与 users.uid 对应，非自增
    "birthday_year": "INTEGER",     # 可空
    "birthday_month": "INTEGER",    # 可空
    "birthday_day": "INTEGER",      # 可空
    "gender": "TEXT",               # "male" / "female" / NULL
    "player_name": "TEXT",          # Minecraft 玩家名，满足 [a-zA-Z0-9_]+
    "followers": "TEXT",            # JSON 数组：关注本用户的 uid 列表
    "followings": "TEXT",           # JSON 数组：本用户关注的 uid 列表
    "profile": "TEXT",              # 个人简介（Markdown 文本）
}


class UserInfoDatabase(UserDatabase, BasicDatabase):
    """存储用户扩展信息（性别、生日）的 sqlite3 数据库。

    与用户基础库共用同一个 ``basic_user_data.db`` 文件，内部表 ``user_info``；
    其 ``uid`` 主键来自 ``users`` 表，因此不是自增列。
    """

    TABLE_NAME = "user_info"
    TABLE_COLUMNS = USER_INFO_TABLE_COLUMNS

    def connect(self) -> None:
        """打开数据库、建表/迁移，并确保 player_name 唯一索引存在。"""
        super().connect()
        self._conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_player_name "
            f"ON {self.TABLE_NAME}(player_name)"
        )
        self._conn.commit()

    def get_user_info(self, uid: int) -> dict[str, Any] | None:
        """按 uid 读取用户扩展信息；不存在返回 None。"""
        row = self._conn.execute(
            f"SELECT * FROM {self.TABLE_NAME} WHERE uid = ?", (uid,)
        ).fetchone()
        return self._row_to_dict(row)

    def set_user_info(
        self,
        uid: int,
        *,
        birthday_year: int | None = None,
        birthday_month: int | None = None,
        birthday_day: int | None = None,
        gender: str | None = None,
    ) -> None:
        """插入或更新指定 uid 的扩展信息（全量 upsert）。"""
        self._conn.execute(
            f"INSERT INTO {self.TABLE_NAME} "
            f"(uid, birthday_year, birthday_month, birthday_day, gender) "
            f"VALUES (?, ?, ?, ?, ?) "
            f"ON CONFLICT(uid) DO UPDATE SET "
            f"birthday_year=excluded.birthday_year, "
            f"birthday_month=excluded.birthday_month, "
            f"birthday_day=excluded.birthday_day, "
            f"gender=excluded.gender",
            (uid, birthday_year, birthday_month, birthday_day, gender),
        )
        self._conn.commit()

    @staticmethod
    def _validate_player_name(player_name: str) -> str:
        """校验玩家名称；不合法时抛出 ValueError。"""
        if not isinstance(player_name, str) or PLAYER_NAME_PATTERN.fullmatch(player_name) is None:
            raise ValueError(f"非法的 player_name: {player_name!r}")
        return player_name

    def player_name_exists(self, player_name: str) -> bool:
        """判断玩家名称是否已被占用。"""
        row = self._conn.execute(
            f"SELECT 1 FROM {self.TABLE_NAME} WHERE player_name = ? LIMIT 1",
            (player_name,),
        ).fetchone()
        return row is not None

    def set_player_name(self, uid: int, player_name: str) -> None:
        """设置玩家的 Minecraft 名称（仅更新 player_name，不影响其它字段）。"""
        player_name = self._validate_player_name(player_name)
        other = self._conn.execute(
            f"SELECT uid FROM {self.TABLE_NAME} WHERE player_name = ? AND uid != ? LIMIT 1",
            (player_name, uid),
        ).fetchone()
        if other is not None:
            raise PlayerNameExistsError(f"玩家名 {player_name!r} 已被占用")
        if self.get_user_info(uid) is None:
            self.set_user_info(uid)  # 预建空行
        self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET player_name = ? WHERE uid = ?",
            (player_name, uid),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # 关注 / 简介
    # ------------------------------------------------------------------

    @staticmethod
    def _json_to_uid_list(raw: Any) -> list[int]:
        """把 followers/followings 的 JSON 文本解析成 uid 列表；空/非法返回 []。"""
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
        """把 uid 列表序列化为 JSON 文本（去重、升序，最小化存储）。"""
        return json.dumps(sorted({int(u) for u in uids}))

    def get_followers(self, uid: int) -> list[int]:
        """返回关注本用户的 uid 列表。"""
        info = self.get_user_info(uid)
        return self._json_to_uid_list(info["followers"]) if info else []

    def get_followings(self, uid: int) -> list[int]:
        """返回本用户关注的 uid 列表。"""
        info = self.get_user_info(uid)
        return self._json_to_uid_list(info["followings"]) if info else []

    def is_following(self, follower_uid: int, target_uid: int) -> bool:
        """判断 follower 是否关注了 target。"""
        return target_uid in self.get_followings(follower_uid)

    def _set_follow_list(self, uid: int, column: str, uids: list[int]) -> None:
        """写入指定关注列（column 仅限内部常量 followers/followings）。"""
        self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET {column} = ? WHERE uid = ?",
            (self._uid_list_to_json(uids), uid),
        )

    def add_follow(self, follower_uid: int, target_uid: int) -> None:
        """follower 关注 target：双方列表各追加一个 uid。"""
        if self.get_user_info(follower_uid) is None:
            self.set_user_info(follower_uid)
        if self.get_user_info(target_uid) is None:
            self.set_user_info(target_uid)
        followings = self.get_followings(follower_uid)
        followers = self.get_followers(target_uid)
        if target_uid not in followings:
            followings.append(target_uid)
        if follower_uid not in followers:
            followers.append(follower_uid)
        self._set_follow_list(follower_uid, "followings", followings)
        self._set_follow_list(target_uid, "followers", followers)
        self._conn.commit()

    def remove_follow(self, follower_uid: int, target_uid: int) -> None:
        """follower 取消关注 target。"""
        followings = [u for u in self.get_followings(follower_uid) if u != target_uid]
        followers = [u for u in self.get_followers(target_uid) if u != follower_uid]
        self._set_follow_list(follower_uid, "followings", followings)
        self._set_follow_list(target_uid, "followers", followers)
        self._conn.commit()

    def purge_user_refs(self, uid: int) -> None:
        """完整清理：从所有其他用户的 followers / followings 列表中移除指定 uid 的引用。"""
        rows = self._conn.execute(
            f"SELECT uid FROM {self.TABLE_NAME}"
        ).fetchall()
        for row in rows:
            other_uid = row["uid"]
            if other_uid == uid:
                continue
            followings = [u for u in self.get_followings(other_uid) if u != uid]
            followers = [u for u in self.get_followers(other_uid) if u != uid]
            self._set_follow_list(other_uid, "followings", followings)
            self._set_follow_list(other_uid, "followers", followers)
        self._conn.commit()

    def set_profile(self, uid: int, profile: str) -> None:
        """设置个人简介（Markdown 文本）。"""
        if self.get_user_info(uid) is None:
            self.set_user_info(uid)
        self._conn.execute(
            f"UPDATE {self.TABLE_NAME} SET profile = ? WHERE uid = ?",
            (profile, uid),
        )
        self._conn.commit()

    def delete_user_info(self, uid: int) -> bool:
        """按 uid 删除扩展信息，返回是否真的删除了。"""
        cursor = self._conn.execute(
            f"DELETE FROM {self.TABLE_NAME} WHERE uid = ?", (uid,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # 键值接口：以 uid（字符串形式）为 key，覆盖父类以 username 为 key 的语义
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        try:
            info = self.get_user_info(int(key))
        except (TypeError, ValueError):
            return default
        return default if info is None else info

    def set(self, key: str, value: Any) -> None:
        if not isinstance(value, dict):
            raise TypeError("value 必须是包含 birthday_year/month/day/gender 的字典")
        try:
            uid = int(key)
        except (TypeError, ValueError):
            raise ValueError(f"非法的 uid key: {key!r}") from None
        self.set_user_info(uid, **value)

    def delete(self, key: str) -> bool:
        try:
            return self.delete_user_info(int(key))
        except (TypeError, ValueError):
            return False

    def keys(self) -> list[str]:
        rows = self._conn.execute(
            f"SELECT uid FROM {self.TABLE_NAME} ORDER BY uid"
        ).fetchall()
        return [str(row["uid"]) for row in rows]