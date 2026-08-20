"""后端路由包：按类拆分路由注册。

每个模块定义一个 APIRouter，路由所需的辅助函数 / 数据库实例 / 常量
（如 get_current_user、_error_response、user_db 等）仍保留在 main.py 中，
由各模块 ``from main import ...`` 引用。
"""
