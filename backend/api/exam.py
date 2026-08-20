"""入服考试路由：考生端（答题/上传/交卷/重审）+ 管理端（试卷/答题卡/改分）。"""
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from data.exam import ExamConfigError, save_exam_config

from main import (
    ERROR_STATUS,
    USERNAME_RE,
    EXAM_IMAGE_DIR,
    EXAM_IMAGE_CONTENT_TYPES,
    EXAM_UPLOAD_DIR,
    EXAM_UPLOAD_CONTENT_TYPES,
    MAX_EXAM_DOC_SIZE,
    MAX_EXAM_IMAGE_SIZE,
    MAX_EXAM_UPLOAD_SIZE,
    _apply_exam_pass,
    _error_response,
    _exam_question_public,
    _grade_exam_question,
    _load_exam,
    _notify_exam_passed,
    _send_email,
    exam_db,
    get_current_user,
    message_db,
    user_db,
    user_info_db,
)

router = APIRouter()


@router.get("/api/exam")
def exam_config(user: dict | None = Depends(get_current_user)):
    """考试配置（不含标准答案，防止作弊）；需登录。"""
    if user is None:
        return _error_response("unauthorized", 401)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    questions = [_exam_question_public(qid, q) for qid, q in cfg["questions"].items()]
    questions.sort(key=lambda x: x["id"])
    return {
        "total_score": cfg["total_score"],
        "tips": cfg.get("tips", ""),
        "tips_doc": cfg.get("tips_doc", ""),
        "questions": questions,
    }


@router.get("/api/exam/progress")
def exam_progress(user: dict | None = Depends(get_current_user)):
    """当前用户答题进度（每题的已答内容 / 附件 / 得分）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    records = exam_db.get_answers(user["uid"])
    answered = {
        qid: {
            "answer": rec.get("answer"),
            "attachment": rec.get("attachment") or [],
            "obtained_score": rec.get("obtained_score", 0),
            "answered_at": rec.get("answered_at"),
        }
        for qid, rec in records.items()
    }
    all_ids = set(cfg["questions"].keys())
    return {
        "answered": answered,
        "answered_count": len(answered),
        "total_questions": len(all_ids),
        "all_answered": all_ids.issubset(answered.keys()),
    }


@router.post("/api/exam/answer")
def exam_answer(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """提交某题答案（每答一题、锁存一题）；自动判分并返回该题得分。"""
    if user is None:
        return _error_response("unauthorized", 401)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    try:
        qid = int(payload.get("question_id"))
    except (TypeError, ValueError):
        return _error_response("exam_question_not_found", 404)
    q = cfg["questions"].get(qid)
    if q is None:
        return _error_response("exam_question_not_found", 404)

    answer = payload.get("answer")
    # 附件：允许文件名列表（多附件）；兼容旧格式单个文件名
    attachment = payload.get("attachment") or None
    if isinstance(attachment, str):
        attachment = [attachment]
    elif not isinstance(attachment, list):
        attachment = None
    options = q.get("options") or {}

    # 按题型校验答案格式
    if q["type"] == "single_choice":
        if not isinstance(answer, str) or answer not in options:
            return _error_response("exam_answer_invalid", 400)
    elif q["type"] == "multiple_choice":
        if not isinstance(answer, list) or not all(
            isinstance(x, str) and x in options for x in answer
        ):
            return _error_response("exam_answer_invalid", 400)
    elif q["type"] == "fill_blank":
        # 单项填空：字符串；多项填空：每空一个字符串组成的列表；允许空答案（None/空串/空数组）
        if answer is not None and not isinstance(answer, str) and not (
            isinstance(answer, list) and all(isinstance(x, str) for x in answer)
        ):
            return _error_response("exam_answer_invalid", 400)
    else:  # subjective 主观题：文本作答，不计分；允许空答案
        if answer is not None and not isinstance(answer, str):
            return _error_response("exam_answer_invalid", 400)
    # 附件仅填空题且 allow_upload 时允许
    if attachment:
        if q["type"] != "fill_blank" or not q.get("allow_upload"):
            return _error_response("exam_upload_not_allowed", 400)

    score, correct = _grade_exam_question(q, answer)
    exam_db.save_answer(user["uid"], qid, answer, score, attachment)
    return {
        "success": True,
        "question_id": qid,
        "obtained_score": score,
        "correct": correct,
    }


@router.post("/api/exam/upload")
async def exam_upload(
    question_id: int = Form(...),
    file: UploadFile = File(...),
    user: dict | None = Depends(get_current_user),
):
    """上传答题附件（图片）；仅填空题且 allow_upload 的题目允许。"""
    if user is None:
        return _error_response("unauthorized", 401)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    q = cfg["questions"].get(question_id)
    if q is None:
        return _error_response("exam_question_not_found", 404)
    if q["type"] != "fill_blank" or not q.get("allow_upload"):
        return _error_response("exam_upload_not_allowed", 400)
    ext = EXAM_UPLOAD_CONTENT_TYPES.get(file.content_type)
    if ext is None:
        return _error_response("exam_upload_unsupported", 400)
    data = await file.read(MAX_EXAM_UPLOAD_SIZE + 1)
    if len(data) > MAX_EXAM_UPLOAD_SIZE:
        return _error_response("exam_upload_too_large", 413)
    filename = f"u{user['uid']}_q{question_id}_{uuid.uuid4().hex}{ext}"
    EXAM_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (EXAM_UPLOAD_DIR / filename).write_bytes(data)
    return {"success": True, "attachment": filename}


@router.get("/api/exam/attachment/{filename}")
def exam_attachment(filename: str, user: dict | None = Depends(get_current_user)):
    """读取答题附件（图片）；仅本人或管理员。"""
    if user is None:
        return _error_response("unauthorized", 401)
    name = Path(filename).name
    match = re.match(r"^u(\d+)_q\d+_[0-9a-f]+\.(jpg|png|webp|gif)$", name)
    if not match:
        return _error_response("exam_attachment_not_found", 404)
    owner = int(match.group(1))
    if owner != user["uid"] and (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    path = EXAM_UPLOAD_DIR / name
    if not path.is_file():
        return _error_response("exam_attachment_not_found", 404)
    return FileResponse(path)


@router.delete("/api/exam/attachment/{filename}")
def delete_exam_attachment(filename: str, user: dict | None = Depends(get_current_user)):
    """删除本人（或管理员）上传的答题附件：移除答题记录引用并删除文件。"""
    if user is None:
        return _error_response("unauthorized", 401)
    name = Path(filename).name
    match = re.match(r"^u(\d+)_q(\d+)_[0-9a-f]+\.(jpg|png|webp|gif)$", name)
    if not match:
        return _error_response("exam_attachment_not_found", 404)
    owner = int(match.group(1))
    question_id = int(match.group(2))
    if owner != user["uid"] and (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    # 从答题记录中移除引用（幂等）
    exam_db.remove_attachment(owner, question_id, name)
    # 删除磁盘文件
    path = EXAM_UPLOAD_DIR / name
    if path.is_file():
        path.unlink()
    return {"success": True}


@router.post("/api/admin/exam/image")
async def admin_upload_exam_image(
    file: UploadFile = File(...),
    user: dict | None = Depends(get_current_user),
):
    """试卷管理：上传试卷附图（题目/选项图片），保存到 data/exam_image，仅管理员。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    ext = EXAM_IMAGE_CONTENT_TYPES.get(file.content_type)
    if ext is None:
        return _error_response("exam_image_unsupported", 400)
    data = await file.read(MAX_EXAM_IMAGE_SIZE + 1)
    if len(data) > MAX_EXAM_IMAGE_SIZE:
        return _error_response("exam_image_too_large", 413)
    filename = f"cfg_{uuid.uuid4().hex}{ext}"
    EXAM_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    (EXAM_IMAGE_DIR / filename).write_bytes(data)
    return {
        "success": True,
        "filename": filename,
        "url": f"/api/exam/image/{filename}",
    }


@router.get("/api/exam/image/{filename}")
def exam_image(filename: str):
    """读取试卷附图（公开，供考试页面显示题目/选项图片）。"""
    name = Path(filename).name
    if name != filename or not re.match(r"^cfg_[0-9a-f]+\.(jpg|png|webp|gif)$", name):
        return _error_response("exam_image_not_found", 404)
    path = EXAM_IMAGE_DIR / name
    if not path.is_file():
        return _error_response("exam_image_not_found", 404)
    return FileResponse(path)


@router.post("/api/admin/exam/doc")
async def admin_upload_exam_doc(
    file: UploadFile = File(...),
    user: dict | None = Depends(get_current_user),
):
    """试卷管理：上传试卷说明文档（仅 .docx），与附图共用 data/exam_image，仅管理员。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    if file.content_type != "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _error_response("exam_doc_unsupported", 400)
    data = await file.read(MAX_EXAM_DOC_SIZE + 1)
    if len(data) > MAX_EXAM_DOC_SIZE:
        return _error_response("exam_doc_too_large", 413)
    filename = f"cfg_doc_{uuid.uuid4().hex}.docx"
    EXAM_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    (EXAM_IMAGE_DIR / filename).write_bytes(data)
    return {
        "success": True,
        "filename": filename,
        "url": f"/api/exam/doc/{filename}",
    }


@router.get("/api/exam/doc/{filename}")
def exam_doc(filename: str):
    """读取试卷说明文档（公开，供考生在线浏览/下载）。"""
    name = Path(filename).name
    if name != filename or not re.match(r"^cfg_doc_[0-9a-f]+\.docx$", name):
        return _error_response("exam_doc_not_found", 404)
    path = EXAM_IMAGE_DIR / name
    if not path.is_file():
        return _error_response("exam_doc_not_found", 404)
    return FileResponse(path)


@router.post("/api/exam/submit")
def exam_submit(user: dict | None = Depends(get_current_user)):
    """交卷汇总：返回总分 / 已得分数 / 完成情况。"""
    if user is None:
        return _error_response("unauthorized", 401)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    records = exam_db.get_answers(user["uid"])
    obtained = sum(rec.get("obtained_score", 0) for rec in records.values())
    all_ids = set(cfg["questions"].keys())
    answered_ids = set(records.keys())
    return {
        "success": True,
        "total_score": cfg["total_score"],
        "obtained_score": obtained,
        "answered_count": len(records),
        "total_questions": len(all_ids),
        "all_answered": answered_ids.issubset(all_ids),
    }


@router.get("/api/exam/profile")
def exam_profile(user: dict | None = Depends(get_current_user)):
    """当前考生信息（游戏名 / 正版状态 / 次数 / 是否及格 / 本答卷是否已申请重审）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    profile = exam_db.get_profile(user["uid"]) or {}
    return {
        "player_name": profile.get("player_name", ""),
        "is_premium": profile.get("is_premium", ""),
        "attempts": int(profile.get("attempts", 0)),
        "passed": bool(profile.get("passed")),
        "review_requested": bool(profile.get("review_requested")),
        "can_answer": exam_db.can_answer(user["uid"]),
    }


@router.post("/api/exam/profile")
def exam_save_profile(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """实时保存个人信息（游戏名称 + 正版状态）。

    正版状态必选（premium/offline，望海不强制要求正版）。
    开始答题前校验：player_name 不得与其它用户的主账号/小号重复
    （因测试可能重置考试库，只检测与其它用户的重复，不判断自身）。
    """
    if user is None:
        return _error_response("unauthorized", 401)
    player_name = str(payload.get("player_name") or "").strip()[:64]
    is_premium = str(payload.get("is_premium") or "").strip()
    if not USERNAME_RE.fullmatch(player_name):
        return _error_response("player_name_invalid", 400)
    if is_premium not in ("premium", "offline"):
        return _error_response("premium_invalid", 400)
    # 全局查重（排除自身）
    if user_info_db.account_name_taken_by_other(user["uid"], player_name):
        return _error_response("player_name_exists", 409)
    exam_db.save_profile(user["uid"], player_name, is_premium)
    # 同步正版标签到 user_info（用户页"管理游戏账户"读取主账号标签）
    user_info_db.set_premium_flag(user["uid"], player_name, is_premium)
    return {"success": True}


@router.post("/api/exam/reset")
def exam_reset(user: dict | None = Depends(get_current_user)):
    """重新作答：清空本人的答题记录（次数限制内允许），并重置本答卷的重审申请标记。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if not exam_db.can_answer(user["uid"]):
        return _error_response("exam_cannot_answer", 403)
    exam_db.delete_answers(user["uid"])
    # 重做 = 进入新的答卷周期：允许再申请一次重审
    exam_db.set_review_requested(user["uid"], False)
    return {"success": True}


@router.post("/api/exam/finish")
def exam_finish(user: dict | None = Depends(get_current_user)):
    """完成答卷：判分汇总、次数 +1；及格则注入 player_name 并升级为 player(2)。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if not exam_db.can_answer(user["uid"]):
        return _error_response("exam_cannot_answer", 403)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    answers = exam_db.get_answers(user["uid"])
    # 允许空答案：未作答的题视为空答案（0 分），不再强制要求每题都有记录

    total = cfg["total_score"]
    obtained = sum(rec.get("obtained_score", 0) for rec in answers.values())
    passed = obtained >= total * 0.6
    if passed:
        err = _apply_exam_pass(user["uid"])
        if err:
            return _error_response(err, ERROR_STATUS.get(err, 400))

    attempts = exam_db.increment_attempts(user["uid"])
    return {
        "success": True,
        "total_score": total,
        "obtained_score": obtained,
        "passed": passed,
        "attempts": attempts,
        "can_answer": exam_db.can_answer(user["uid"]),
    }


@router.post("/api/exam/review")
def exam_review(user: dict | None = Depends(get_current_user)):
    """申请重审答题卡：向所有管理员推送定向消息并发送邮件。

    防连点：本答卷周期（一次答题机会）内只允许申请一次；
    重做（/api/exam/reset）进入新答卷周期后允许再次申请。
    """
    if user is None:
        return _error_response("unauthorized", 401)
    if exam_db.is_review_requested(user["uid"]):
        return _error_response("exam_review_already_requested", 400)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    answers = exam_db.get_answers(user["uid"])
    if not answers:
        return _error_response("exam_answers_not_found", 404)
    obtained = sum(rec.get("obtained_score", 0) for rec in answers.values())
    profile = exam_db.get_profile(user["uid"]) or {}
    target = user_db.get_user(uid=user["uid"])
    admins = [u for u in user_db.list_users() if (u.get("permission") or 0) >= 3]

    title = "答题卡重审申请"
    content = (
        f"用户 {target['username']}（UID {user['uid']}）申请重审答题卡。\n"
        f"游戏名称：{profile.get('player_name', '')}\n"
        f"当前得分：{obtained} / {cfg['total_score']}\n"
        f"请管理员前往「考试管理」查看该用户的答题卡。"
    )
    sent = 0
    for admin in admins:
        message_db.create_message(
            title, content, user["uid"], scope="user", target_uid=admin["uid"]
        )
        _send_email(
            admin["email"],
            f"[望海服务器] 答题卡重审申请 - {target['username']}",
            content,
            "zh",
        )
        sent += 1
    exam_db.set_review_requested(user["uid"], True)
    return {"success": True, "notified": sent}


@router.get("/api/admin/exam/candidates")
def admin_exam_candidates(
    page: int = 1,
    page_size: int = 10,
    user: dict | None = Depends(get_current_user),
):
    """考试管理：有答卷的考生列表（分页）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    uids = exam_db.list_answered_uids()
    total = len(uids)
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    items = uids[(page - 1) * page_size : page * page_size]
    result = []
    for uid in items:
        u = user_db.get_user(uid=uid)
        if u is None:
            continue
        prof = exam_db.get_profile(uid) or {}
        result.append({
            "uid": uid,
            "username": u["username"],
            "avatar": u.get("avatar"),
            "player_name": prof.get("player_name") or "",
            "attempts": int(prof.get("attempts", 0)),
            "passed": bool(prof.get("passed")),
            "answered_count": len(exam_db.get_answers(uid)),
        })
    return {"total": total, "page": page, "page_size": page_size, "candidates": result}


@router.get("/api/admin/exam/config")
def admin_exam_config(user: dict | None = Depends(get_current_user)):
    """试卷管理：管理员获取完整试卷配置（含标准答案，用于在线编辑）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    return cfg


@router.put("/api/admin/exam/config")
def admin_save_exam_config(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """试卷管理：管理员保存试卷配置（校验通过后写回 exam.yml，即时生效）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    try:
        validated = save_exam_config(payload)
    except ExamConfigError as exc:
        print(f"[exam-config] 保存失败: {exc}", flush=True)
        return _error_response("exam_config_invalid", 400)
    return {"success": True, "config": validated}


@router.get("/api/admin/exam/answers/{uid}")
def admin_exam_answers(uid: int, user: dict | None = Depends(get_current_user)):
    """查看某考生答题卡（题目 + 答案 + 得分）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    answers = exam_db.get_answers(uid)
    if not answers:
        return _error_response("exam_answers_not_found", 404)
    profile = exam_db.get_profile(uid) or {}
    per = {}
    for qid, q in cfg["questions"].items():
        rec = answers.get(qid)
        per[qid] = {
            "question": _exam_question_public(qid, q),
            "answer": rec.get("answer") if rec else None,
            "attachment": (rec.get("attachment") or []) if rec else [],
            "obtained_score": rec.get("obtained_score", 0) if rec else 0,
            "answered": rec is not None,
        }
    total = cfg["total_score"]
    obtained = sum(rec.get("obtained_score", 0) for rec in answers.values())
    return {
        "uid": uid,
        "profile": profile,
        "answers": per,
        "total_score": total,
        "obtained_score": obtained,
    }


@router.post("/api/admin/exam/score")
def admin_exam_score(payload: dict = Body(...), user: dict | None = Depends(get_current_user)):
    """管理员修改某考生某题的实际得分（0 ~ 该题满分）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    try:
        uid = int(payload.get("uid"))
        question_id = int(payload.get("question_id"))
    except (TypeError, ValueError):
        return _error_response("exam_score_invalid", 400)
    score = payload.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool) or score < 0:
        return _error_response("exam_score_invalid", 400)
    cfg = _load_exam()
    if cfg is None:
        return _error_response("exam_config_error", 500)
    q = cfg["questions"].get(question_id)
    if q is None:
        return _error_response("exam_question_not_found", 404)
    if int(score) > int(q.get("score", 0)):
        return _error_response("exam_score_invalid", 400)
    if exam_db.get_answer(uid, question_id) is None:
        return _error_response("exam_answers_not_found", 404)
    exam_db.set_score(uid, question_id, int(score))
    # 改分后重新汇总总分并判定及格状态（达标且未通过则应用及格处理）
    records = exam_db.get_answers(uid)
    obtained_total = sum(r.get("obtained_score", 0) for r in records.values())
    passed_now = obtained_total >= cfg["total_score"] * 0.6
    passed_flag = bool((exam_db.get_profile(uid) or {}).get("passed"))
    if passed_now and not passed_flag:
        err = _apply_exam_pass(uid)
        if err:
            return _error_response(err, ERROR_STATUS.get(err, 400))
        # 复审通过：通知考生（消息盒子定向消息 + 邮件）
        _notify_exam_passed(uid, user["uid"])
    return {"success": True, "obtained_score": int(score), "passed": passed_now}


@router.delete("/api/admin/exam/answers/{uid}")
def admin_exam_delete_answers(uid: int, user: dict | None = Depends(get_current_user)):
    """删除某考生答卷（重置：清空答题记录、次数与及格标记，允许重新作答）。"""
    if user is None:
        return _error_response("unauthorized", 401)
    if (user.get("permission") or 0) < 3:
        return _error_response("permission_denied", 403)
    exam_db.reset_candidate(uid)
    return {"success": True}
