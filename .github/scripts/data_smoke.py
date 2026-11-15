#!/usr/bin/env python3
"""数据层 CI 冒烟检查（data/）。

由 .github/workflows/ci.yml 的「数据层」job 调用；也可本地直接运行：

    python .github/scripts/data_smoke.py

检查内容：
1. SQLite / FTS5 能力探测（FTS5 不可用时维基搜索自动回退 LIKE，仅告警）；
2. data/ 下全部 Python 文件的语法编译；
3. 考试配置解析 data/exam.py：合法配置规范化、非法配置被拒绝、填空答案规范化；
4. 颜色代码剥离工具 data/main/database/text_utils.py；
5. 五个 SQLite 数据库（users/user_info、messages、feedback、exam、wiki）
   的真实建表与增删查改，以及维基欢迎页种子内容。

隔离策略：把 basic_database.DATABASE_DIR 重定向到临时目录后再建库，
因此不会读写仓库里的 data/database/ 真实数据（可安全重复运行）。
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_passed = 0


def section(title: str) -> None:
    print(f"\n===== {title} =====", flush=True)


def ok(message: str) -> None:
    global _passed
    _passed += 1
    print(f"[PASS] {message}", flush=True)


def warn(message: str) -> None:
    print(f"::warning::{message}", flush=True)
    print(f"[WARN] {message}", flush=True)


def fail(message: str) -> None:
    print(f"::error::{message}", flush=True)
    print(f"[FAIL] {message}", flush=True)
    raise SystemExit(1)


def check(condition, message: str) -> None:
    if not condition:
        fail(message)
    ok(message)


# ---------------------------------------------------------------------------
# 1. SQLite 能力探测
# ---------------------------------------------------------------------------
def probe_sqlite() -> None:
    section("SQLite 能力")
    print(f"[INFO] Python {sys.version.split()[0]} / sqlite3 {sqlite3.sqlite_version}")
    fts5 = False
    try:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE ci_probe_fts USING fts5(x, tokenize='trigram')"
            )
        finally:
            conn.close()
        fts5 = True
    except sqlite3.OperationalError as exc:
        warn(f"SQLite 未启用 FTS5/trigram（{exc}）；维基搜索会自动回退 LIKE，冒烟继续。")
    if fts5:
        ok("SQLite FTS5（trigram 分词）可用，维基全文搜索走 FTS 路径")


# ---------------------------------------------------------------------------
# 2. 语法编译
# ---------------------------------------------------------------------------
def check_syntax() -> None:
    section("Python 语法")
    files = sorted((REPO_ROOT / "data").rglob("*.py"))
    for path in files:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            fail(f"语法错误：{path.relative_to(REPO_ROOT)}: {exc}")
    ok(f"data/ 下 {len(files)} 个 Python 文件均通过语法编译")


# ---------------------------------------------------------------------------
# 3. 考试 YAML 解析
# ---------------------------------------------------------------------------
GOOD_EXAM_YAML = """\
total_score: 30
tips: "CI 试卷"
questions:
  1:
    type: single_choice
    subject: "单选题"
    score: 10
    options:
      a: {text: "选项 A"}
      b: {text: "选项 B"}
    answer: a
  2:
    type: multiple_choice
    subject: "多选题"
    score: 10
    options:
      a: {text: "选项 A"}
      b: {text: "选项 B"}
      c: {text: "选项 C"}
    answer: [a, b]
  3:
    type: fill_blank
    subject: "填空题"
    score: 5
    answer: [["foo", "bar"], ["baz"]]
  4:
    type: subjective
    subject: "主观题"
    score: 5
    answer: "参考答案"
"""

INVALID_EXAMS = {
    "YAML 语法错误": "questions: [",
    "total_score 为负": (
        "total_score: -1\n"
        "questions: {1: {type: single_choice, subject: 题, score: 1, "
        "options: {a: {text: A}}, answer: a}}"
    ),
    "未知题型": "total_score: 1\nquestions: {1: {type: essay, subject: 题, score: 1}}",
    "选择题缺选项": "total_score: 1\nquestions: {1: {type: single_choice, subject: 题, score: 1}}",
    "分数为负": "total_score: 1\nquestions: {1: {type: fill_blank, subject: 题, score: -1}}",
}


def check_exam_parser() -> None:
    section("考试 YAML 解析（data/exam.py）")
    from data.exam import (
        ExamConfigError,
        fill_blank_blanks,
        parse_exam_yaml,
        validate_exam_dict,
    )

    validated = validate_exam_dict(parse_exam_yaml(GOOD_EXAM_YAML))
    check(validated["total_score"] == 30, "total_score 解析为 30")
    check(sorted(validated["questions"]) == [1, 2, 3, 4], "题目 id 规范化为整数键")
    check(validated["questions"][1]["answer"] == "a", "单选题 answer 保留")
    check(validated["questions"][2]["answer"] == ["a", "b"], "多选题 answer 为列表")
    check(
        validated["questions"][3]["answer"] == [["foo", "bar"], ["baz"]],
        "多空填空题 answer 原样保留",
    )
    check(validated["questions"][4]["score"] == 0, "主观题分值规范化为 0")
    check(validated["tips"] == "CI 试卷", "tips 保留")

    check(fill_blank_blanks(["甲", "乙"]) == [["甲", "乙"]], "单空多可接受答案规范化")
    check(fill_blank_blanks([["甲"], ["乙"]]) == [["甲"], ["乙"]], "多空答案规范化")
    check(fill_blank_blanks(None) == [], "空答案规范化为空列表")

    for name, text in INVALID_EXAMS.items():
        try:
            validate_exam_dict(parse_exam_yaml(text))
        except ExamConfigError:
            ok(f"非法配置被拒绝：{name}")
        else:
            fail(f"非法配置未被拒绝：{name}")


# ---------------------------------------------------------------------------
# 4. 颜色代码剥离
# ---------------------------------------------------------------------------
def check_text_utils() -> None:
    section("文本工具（MC 颜色代码剥离）")
    from data.main.database.text_utils import strip_mc_color_codes

    check(strip_mc_color_codes("§e§l金色粗体§r普通") == "金色粗体普通", "剥离 16 色 / 格式 / 复位代码")
    check(strip_mc_color_codes("§#FFAA00橙色") == "橙色", "剥离 §#RRGGBB 十六进制颜色")
    check(strip_mc_color_codes("§z未知代码") == "§z未知代码", "未知 § 组合保持原样")
    check(strip_mc_color_codes("无代码") == "无代码", "无颜色代码时原样返回")


# ---------------------------------------------------------------------------
# 5. SQLite 数据库
# ---------------------------------------------------------------------------
def check_databases() -> None:
    section("SQLite 数据层（写入重定向到临时目录）")
    temp_dir = Path(tempfile.mkdtemp(prefix="whs-ci-database-"))
    try:
        # 先把数据库目录重定向到临时目录，再导入具体数据库类。
        import data.main.database.basic_database as basic_db

        basic_db.DATABASE_DIR = temp_dir
        check(basic_db.DATABASE_DIR == temp_dir, f"数据库目录重定向：{temp_dir}")

        from data.main.database.exam_database import ExamDatabase
        from data.main.database.feedback_database import (
            FeedbackDatabase,
            FeedbackDatabaseError,
        )
        from data.main.database.message_database import MessageDatabase
        from data.main.database.user_database import (
            EmailExistsError,
            UserDatabase,
            UserInfoDatabase,
            UsernameExistsError,
        )
        from data.main.database.wiki_database import (
            WikiDatabase,
            WikiRedirectInvalidError,
            WikiRevisionConflictError,
        )

        # --- users / user_info -------------------------------------------
        user_db = UserDatabase()
        user_db.connect()
        info_db = UserInfoDatabase()
        info_db.connect()
        try:
            check("users" in user_db.list_tables(), "users 表已创建")
            check("user_info" in info_db.list_tables(), "user_info 表已创建")

            uid1 = user_db.create_user("ci_user1", "ci_user1@example.com", "CI 用户一", "0" * 64)
            uid2 = user_db.create_user("ci_user2", "ci_user2@example.com", "CI 用户二", "1" * 64)
            check(uid1 > 0 and uid2 > uid1, "create_user 返回递增 uid")
            check(user_db.get_user(uid=uid1)["username"] == "ci_user1", "按 uid 查询用户")
            check(
                user_db.get_user(username="ci_user2")["email"] == "ci_user2@example.com",
                "按 username 查询用户",
            )
            check(
                user_db.get_user(email="ci_user1@example.com")["uid"] == uid1,
                "按 email 查询用户",
            )

            try:
                user_db.create_user("ci_user1", "ci_other@example.com", password="0" * 64)
            except UsernameExistsError:
                ok("重复用户名抛出 UsernameExistsError")
            else:
                fail("重复用户名未抛出 UsernameExistsError")

            try:
                user_db.create_user("ci_user3", "ci_user1@example.com", password="0" * 64)
            except EmailExistsError:
                ok("重复邮箱抛出 EmailExistsError")
            else:
                fail("重复邮箱未抛出 EmailExistsError")

            user_db.set_permission(uid1, 2)
            check(user_db.get_user(uid=uid1)["permission"] == 2, "set_permission 生效")
            user_db.set_locked(uid1, True)
            check(bool(user_db.get_user(uid=uid1)["locked"]), "set_locked 生效")
            user_db.set_banned(uid2, True)
            check(bool(user_db.get_user(uid=uid2)["banned"]), "set_banned 生效")
            user_db.update_user(uid1, fullname="CI 用户一号", avatar="ci.png")
            check(user_db.get_user(uid=uid1)["fullname"] == "CI 用户一号", "update_user 更新字段")
            check(len(user_db.list_users()) == 2, "list_users 返回 2 个用户")
            check(
                any(row["uid"] == uid1 for row in user_db.search_users("ci_user1")),
                "search_users 可命中用户名",
            )

            info_db.set_user_info(
                uid1, birthday_year=2000, birthday_month=1, birthday_day=2, gender="other"
            )
            info = info_db.get_user_info(uid1) or {}
            check(info.get("birthday_year") == 2000, "set_user_info / get_user_info 生效")

            info_db.set_player_name(uid1, "CI_Player")
            check(info_db.get_uid_by_player_name("CI_Player") == uid1, "按玩家名反查 uid")
            info_db.add_alt_account(uid1, "CI_Alt", "offline")
            check(info_db.get_alt_accounts(uid1) == ["CI_Alt"], "小号添加")
            check(info_db.player_name_exists("CI_Alt"), "小号参与玩家名查重")
            info_db.set_premium_flag(uid1, "CI_Player", "premium")
            check(
                info_db.get_premium_flags(uid1).get("CI_Player") == "premium",
                "正版标签设置",
            )
            info_db.set_profile(uid1, "CI 个人简介")
            check((info_db.get_user_info(uid1) or {}).get("profile") == "CI 个人简介", "个人简介设置")

            info_db.add_follow(uid1, uid2)
            check(uid2 in info_db.get_followings(uid1), "add_follow 写入关注列表")
            check(uid1 in info_db.get_followers(uid2), "add_follow 写入粉丝列表")
            info_db.remove_follow(uid1, uid2)
            check(uid2 not in info_db.get_followings(uid1), "remove_follow 移除关注")
            info_db.remove_alt_account(uid1, "CI_Alt")
            check(info_db.get_alt_accounts(uid1) == [], "小号移除")

            check(user_db.delete_user(uid2) is True, "delete_user 删除用户")
            check(user_db.get_user(uid=uid2) is None, "删除后按 uid 查不到")
        finally:
            info_db.close()
            user_db.close()

        # --- messages -----------------------------------------------------
        message_db = MessageDatabase()
        message_db.connect()
        try:
            check("messages" in message_db.list_tables(), "messages 表已创建")
            system_id = message_db.create_message("CI 系统消息", "消息正文", 0)
            user_msg_id = message_db.create_message(
                "CI 定向消息", "定向正文", 0, scope="user", target_uid=1
            )
            check(message_db.get_message(system_id)["title"] == "CI 系统消息", "create_message / get_message")
            check(
                any(item["id"] == system_id for item in message_db.list_system_messages()),
                "list_system_messages 命中系统消息",
            )
            check(
                any(item["id"] == user_msg_id for item in message_db.list_user_messages(1)),
                "list_user_messages 命中定向消息",
            )
            check(message_db.add_read_user(system_id, 7) is True, "add_read_user 标记已读")
            check(message_db.is_read_by(system_id, 7), "is_read_by 已读判断")
            check(message_db.get_read_uids(system_id) == [7], "get_read_uids 读取已读列表")
            check(
                message_db.update_message(system_id, "CI 系统消息（改）", "消息正文（改）") is True,
                "update_message 更新消息",
            )
            check(message_db.get_read_uids(system_id) == [], "编辑消息后清空已读状态")
            check(message_db.delete_message(system_id) is True, "delete_message 删除消息")
            check(message_db.get_message(system_id) is None, "删除后消息不存在")
        finally:
            message_db.close()

        # --- feedback -----------------------------------------------------
        feedback_db = FeedbackDatabase()
        feedback_db.connect()
        try:
            check("feedback" in feedback_db.list_tables(), "feedback 表已创建")
            check("feedback_comments" in feedback_db.list_tables(), "feedback_comments 表已创建")
            feedback_id = feedback_db.create_feedback(
                "CI 反馈", "反馈正文 **markdown**", "bug", 1
            )
            item = feedback_db.get_feedback(feedback_id) or {}
            check(item.get("category") == "bug" and item.get("status") == "pending", "create_feedback 默认状态")

            try:
                feedback_db.create_feedback("非法分类", "正文", "not-a-category", 1)
            except FeedbackDatabaseError as exc:
                check(exc.code == "feedback_category_invalid", "非法分类返回稳定错误码")
            else:
                fail("非法分类未抛出 FeedbackDatabaseError")

            page = feedback_db.list_feedbacks(page=1, page_size=5)
            check(page["total"] >= 1 and page["items"], "list_feedbacks 分页返回")
            check(feedback_db.set_status(feedback_id, "resolved") is True, "set_status 更新状态")
            check((feedback_db.get_feedback(feedback_id) or {}).get("status") == "resolved", "状态已更新")
            comment_id = feedback_db.add_comment(feedback_id, 2, "CI 评论")
            check(
                (feedback_db.get_comment(comment_id) or {}).get("content") == "CI 评论",
                "add_comment / get_comment",
            )
            check(len(feedback_db.list_comments(feedback_id)) == 1, "list_comments 返回 1 条")
            check(
                any(row["id"] == feedback_id for row in feedback_db.search_feedbacks("CI 反馈")),
                "search_feedbacks 命中",
            )
            check(
                feedback_db.update_feedback(feedback_id, "CI 反馈（改）", "新正文", "suggestion") is True,
                "update_feedback 更新反馈",
            )
            check(feedback_db.delete_feedback(feedback_id) is True, "delete_feedback 删除反馈")
            check(feedback_db.get_feedback(feedback_id) is None, "删除后反馈不存在")
        finally:
            feedback_db.close()

        # --- exam ---------------------------------------------------------
        exam_db = ExamDatabase()
        exam_db.connect()
        try:
            check("exam_answers" in exam_db.list_tables(), "exam_answers 表已创建")
            check("exam_profiles" in exam_db.list_tables(), "exam_profiles 表已创建")
            exam_db.save_profile(1, "CI_Player", "offline")
            check((exam_db.get_profile(1) or {}).get("player_name") == "CI_Player", "save_profile / get_profile")
            exam_db.save_answer(1, 1, "a", 10)
            exam_db.save_answer(1, 2, ["a", "b"], 5, ["ci.png"])
            answer = exam_db.get_answer(1, 1) or {}
            check(answer.get("answer") == "a" and answer.get("obtained_score") == 10, "save_answer / get_answer")
            check(len(exam_db.get_answers(1)) == 2, "get_answers 返回 2 条")
            check(
                (exam_db.get_answer(1, 2) or {}).get("attachment") == ["ci.png"],
                "答题附件列表读写",
            )
            exam_db.set_score(1, 1, 8)
            check((exam_db.get_answer(1, 1) or {}).get("obtained_score") == 8, "set_score 改分")
            check(exam_db.increment_attempts(1) == 1, "increment_attempts 次数 +1")
            check(exam_db.can_answer(1) is True, "未及格且次数 < 2 时可继续答题")
            exam_db.mark_passed(1)
            check((exam_db.get_profile(1) or {}).get("passed") == 1, "mark_passed 标记及格")
            check(exam_db.can_answer(1) is False, "及格后不可再答题")
            exam_db.set_review_requested(1, True)
            check(exam_db.is_review_requested(1) is True, "重审申请标记")
            check(1 in exam_db.list_answered_uids(), "list_answered_uids 命中")
            exam_db.reset_candidate(1)
            check(exam_db.get_answers(1) == {}, "reset_candidate 清空答题记录")
            check(int((exam_db.get_profile(1) or {}).get("attempts", -1)) == 0, "reset_candidate 重置次数")
        finally:
            exam_db.close()

        # --- wiki ---------------------------------------------------------
        wiki_db = WikiDatabase()
        wiki_db.connect()
        try:
            tables = wiki_db.list_tables()
            check({"pages", "revisions", "redirects"} <= set(tables), "pages / revisions / redirects 表已创建")
            welcome = wiki_db.get_page("welcome")
            check(welcome is not None, "空库自动播种欢迎页")
            if welcome:
                content_zh = welcome.get("content_zh") or ""
                check("欢迎来到望海服务器维基" in content_zh, "欢迎页中文内容已播种")
                check("§e§l" in content_zh, "欢迎页包含颜色代码说明示例（§e§l）")
                check(bool(welcome.get("content_en")), "欢迎页英文内容已播种")
                check(len(wiki_db.list_revisions(welcome["id"], lang="zh")) >= 1, "欢迎页有修订历史")
            check(
                any(item["slug"] == "welcome" for item in wiki_db.list_pages()),
                "list_pages 包含欢迎页",
            )
            check(
                any(item["slug"] == "welcome" for item in wiki_db.search_pages("欢迎", lang="zh")),
                "短查询（LIKE 路径）可搜到欢迎页",
            )
            check(
                any(item["slug"] == "welcome" for item in wiki_db.search_pages("欢迎来到", lang="zh")),
                "长查询（FTS 或 LIKE 回退）可搜到欢迎页",
            )

            page = wiki_db.create_page("ci-test-page", "# CI 测试页\n\n第一版正文", author_uid=0, lang="zh")
            check(page.get("slug") == "ci-test-page", "create_page 创建页面")
            check(wiki_db.get_page("ci-test-page") is not None, "get_page 读取新页面")
            wiki_db.update_page("ci-test-page", "# CI 测试页\n\n第二版正文", author_uid=1, lang="zh", base_rev=1)
            check(
                len(wiki_db.list_revisions(page["id"], lang="zh")) == 2,
                "update_page 追加修订（rev 2）",
            )
            try:
                wiki_db.update_page("ci-test-page", "# 冲突", author_uid=1, lang="zh", base_rev=999)
            except WikiRevisionConflictError:
                ok("错误 base_rev 触发乐观锁冲突")
            else:
                fail("错误 base_rev 未触发 WikiRevisionConflictError")
            wiki_db.update_page("ci-test-page", "# CI Page\n\nEnglish body", author_uid=1, lang="en")
            check(
                bool((wiki_db.get_page("ci-test-page") or {}).get("content_en")),
                "多语言页面（en）写入",
            )
            wiki_db.set_min_permission("ci-test-page", 3)
            check(
                int((wiki_db.get_page("ci-test-page") or {}).get("min_permission")) == 3,
                "set_min_permission 更新最小编辑权限",
            )
            redirect = wiki_db.create_redirect("ci-old-page", "welcome")
            check(redirect.get("to_slug") == "welcome", "create_redirect 创建重定向")
            check(wiki_db.resolve_redirect("ci-old-page") == "welcome", "resolve_redirect 解析重定向")
            try:
                wiki_db.create_redirect("welcome", "welcome")
            except WikiRedirectInvalidError:
                ok("重定向指向自身被拒绝")
            else:
                fail("重定向指向自身未被拒绝")
            check(wiki_db.delete_redirect("ci-old-page") is True, "delete_redirect 删除重定向")
            check(wiki_db.delete_page("ci-test-page") is True, "delete_page 删除页面")
            check(wiki_db.get_page("ci-test-page") is None, "删除后页面不存在")
        finally:
            wiki_db.close()

        db_files = sorted(p.name for p in temp_dir.glob("*.db"))
        check(
            len(db_files) == 5,
            f"生成 5 个数据库文件（实际 {len(db_files)} 个：{', '.join(db_files)}）",
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> int:
    print("数据层 CI 冒烟检查开始……", flush=True)
    probe_sqlite()
    check_syntax()
    check_exam_parser()
    check_text_utils()
    check_databases()
    print(f"\n全部通过：{_passed} 项检查 PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
