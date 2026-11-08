# -*- coding: utf-8 -*-
"""
管理员工具：按 uid 解锁被锁定的用户账号（连续输错密码/验证码 5 次后锁定）。

用法（在项目根目录运行）：
    python unlock_user.py              # 交互式：逐个输入 uid 解锁，输入 q 退出
    python unlock_user.py 1 2 66       # 或直接传一个/多个 uid

说明：
- 直接读写后端同一数据库 data/database/basic_user_data.db，无需启动服务器；
- 解锁后，用户用正确密码/验证码登录成功即会重置失败计数；
  注意：若后端正在运行，其内存中的失败计数不会因本脚本清零——解锁后如果
  先又输错一次，可能立刻再次触发锁定。稳妥做法：解锁后让用户直接登录成功，
  或重启后端（内存计数自然清零）。
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Windows 控制台中文输出兼容（GBK 终端下防止 UnicodeEncodeError）
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from data.main.database.user_database import UserDatabase


def describe(u: dict) -> str:
    """一行展示用户关键信息。"""
    locked = "🔒 已锁定" if u.get("locked") else "✓ 正常"
    return (
        f"uid={u['uid']}  username={u['username']}  "
        f"email={u.get('email') or '-'}  permission={u.get('permission')}  {locked}"
    )


def unlock_one(db: UserDatabase, uid: int) -> None:
    u = db.get_user(uid=uid)
    if u is None:
        print(f"[!] uid={uid} 的用户不存在")
        return
    if not u.get("locked"):
        print(f"[=] {describe(u)}  —— 未被锁定，无需解锁")
        return

    # 先展示锁定信息，确认后解锁
    print(f"[?] 即将解锁：{describe(u)}")
    try:
        confirm = input("    确认解锁？(y/N) ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消")
        return
    if confirm not in ("y", "yes"):
        print("    已取消")
        return

    db.set_locked(uid, False)
    after = db.get_user(uid=uid)
    if after and not after.get("locked"):
        print(f"[✓] 解锁成功：uid={uid} ({u['username']})，现在可以正常登录了")
    else:
        print(f"[✗] 解锁失败，请检查数据库状态")


def main() -> None:
    db = UserDatabase()
    db.connect()

    # 命令行参数模式：python unlock_user.py 1 2 66
    args = [a for a in sys.argv[1:] if a.strip()]
    if args:
        for raw in args:
            try:
                unlock_one(db, int(raw))
            except ValueError:
                print(f"[!] 无效 uid：{raw!r}")
        db.close()
        return

    # 交互模式：可连续解锁多个，输入 q 退出
    print("=== 用户账号解锁工具 ===")
    print("输入 uid 解锁用户；输入 q 退出")
    print("（也可用命令行参数一次解锁多个：python unlock_user.py 1 2 66）")
    print("-" * 50)
    try:
        while True:
            raw = input("uid> ").strip()
            if raw.lower() in ("q", "quit", "exit"):
                print("再见")
                break
            if not raw:
                continue
            try:
                unlock_one(db, int(raw))
            except ValueError:
                print(f"[!] 无效 uid：{raw!r}，请输入数字")
            print("-" * 50)
    except (EOFError, KeyboardInterrupt):
        print("\n再见")
    finally:
        db.close()


if __name__ == "__main__":
    main()
