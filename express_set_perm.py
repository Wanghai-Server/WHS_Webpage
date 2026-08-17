"""临时脚本：把指定用户设为管理员（permission=3）。运行后删除本文件。"""
import sqlite3

con = sqlite3.connect("data/database/basic_user_data.db")
print("=== 当前用户列表 (uid, username, email, permission) ===")
for r in con.execute("SELECT uid, username, email, permission FROM users ORDER BY uid"):
    print(r)

uid = input("\n输入要设为管理员的 uid: ").strip()
perm = input("输入权限值 (0=guest 1=user 2=player 3=admin 4=owner，回车默认 3): ").strip() or "3"
try:
    uid = int(uid)
    perm = int(perm)
    if not 0 <= perm <= 4:
        raise ValueError("权限值须为 0~4")
except ValueError as exc:
    print(f"输入无效: {exc}")
    con.close()
    raise SystemExit(1)

n = con.execute("UPDATE users SET permission = ? WHERE uid = ?", (perm, uid)).rowcount
con.commit()
if n == 0:
    print(f"uid={uid} 不存在，未做修改")
else:
    print("修改成功，当前记录：")
    print(list(con.execute("SELECT uid, username, permission FROM users WHERE uid = ?", (uid,))))
con.close()
