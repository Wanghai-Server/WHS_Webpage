"""数据库访问抽象基类。

定义统一的数据访问接口。具体的存储后端（如 JSON 文件、SQLite 等）
只需继承 :class:`BasicDatabase` 并实现其中标记为 ``@abstractmethod``
的方法即可，其余通用逻辑（路径规范化、目录创建、连接状态管理）由基类统一提供。

所有数据库文件统一存放在 ``data/database/`` 目录中（该目录锚定到本包所在的
``data`` 目录，与运行时工作目录无关），并以 ``.db`` 作为后缀。
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

# 数据库文件的统一存放目录：固定锚定到本包所在项目内的 data/database。
# basic_database.py 位于 <项目根>/data/main/database/ 下，
# 向上三级即 <项目根>/data/，再拼接 "database" 得到 <项目根>/data/database/。
DATABASE_DIR = Path(__file__).resolve().parent.parent.parent / "database"


class BasicDatabase(ABC):
    """所有数据库实现的公共抽象接口。"""

    def __init__(self, database_path: str) -> None:
        super().__init__()
        # 无论传入何种路径，最终都统一规范化到 data/database/<名称>.db。
        self.database_path = self._normalize_database_path(database_path)
        self._connection = None
        self._connected = False

    # ------------------------------------------------------------------
    # 路径处理
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_database_path(database_path: str) -> str:
        """将传入路径规范化为 ``data/database/<名称>.db``。

        仅保留文件名部分、忽略传入的目录，并确保以 ``.db`` 结尾。
        """
        name = Path(database_path).name
        if not name:
            raise ValueError("数据库文件名不能为空")
        if not name.endswith(".db"):
            name += ".db"
        return str(DATABASE_DIR / name)

    @property
    def is_connected(self) -> bool:
        """当前是否已建立连接。"""
        return self._connected

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    @abstractmethod
    def connect(self) -> None:
        """建立连接（或加载数据文件）。

        子类必须实现，并应在实现开头调用 ``super().connect()``，
        以完成通用初始化（创建数据库目录、标记连接状态）。
        """
        DATABASE_DIR.mkdir(parents=True, exist_ok=True)
        self._connected = True

    @abstractmethod
    def close(self) -> None:
        """关闭连接并释放相关资源。

        子类必须实现，并应在实现末尾调用 ``super().close()``，
        以完成通用清理（重置连接状态）。
        """
        self._connection = None
        self._connected = False

    def __enter__(self) -> "BasicDatabase":
        """作为上下文管理器进入时自动连接。"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """作为上下文管理器退出时自动关闭。"""
        self.close()

    # ------------------------------------------------------------------
    # 数据表管理
    # ------------------------------------------------------------------

    @abstractmethod
    def create_table(
        self,
        table_name: str,
        columns: dict[str, str] | None = None,
        *,
        if_not_exists: bool = True,
    ) -> None:
        """创建数据表。

        :param table_name: 表名。
        :param columns: 列名到列定义的映射，例如
            ``{"id": "INTEGER PRIMARY KEY", "name": "TEXT NOT NULL"}``。
            对于非关系型后端（如 JSON 文档存储）可传 ``None``。
        :param if_not_exists: 表已存在时是否静默跳过（``True``）而非报错。
        """

    @abstractmethod
    def drop_table(self, table_name: str, *, if_exists: bool = False) -> None:
        """删除数据表。

        :param table_name: 表名。
        :param if_exists: 表不存在时是否静默跳过（``True``）而非报错。
        """

    @abstractmethod
    def list_tables(self) -> list[str]:
        """返回当前数据库中所有数据表的名称列表。"""

    # ------------------------------------------------------------------
    # 数据读写
    # ------------------------------------------------------------------

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """读取 ``key`` 对应的值；不存在时返回 ``default``。"""

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """写入（新增或覆盖）一条数据。"""

    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除 ``key`` 对应的数据，返回是否真的发生了删除。"""

    @abstractmethod
    def keys(self) -> list[str]:
        """返回当前所有 ``key`` 的列表。"""

    # ------------------------------------------------------------------
    # 基于上述抽象方法的默认实现（子类可按需覆盖以优化）
    # ------------------------------------------------------------------

    def exists(self, key: str) -> bool:
        """判断 ``key`` 是否存在。"""
        return key in self.keys()

    def clear(self) -> None:
        """清空全部数据。"""
        for key in self.keys():
            self.delete(key)

    def __contains__(self, key: str) -> bool:
        """支持 ``key in db`` 的写法。"""
        return self.exists(key)

    def __len__(self) -> int:
        """返回当前数据条目总数。"""
        return len(self.keys())

    def __repr__(self) -> str:
        return f"{type(self).__name__}(database_path={self.database_path!r})"
