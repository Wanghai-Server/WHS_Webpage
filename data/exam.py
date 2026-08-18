"""考试配置解析器。

从 ``data/exam.yml`` 读取考试内容（YAML）并解析、校验为规范结构。
解析使用 PyYAML 的 ``yaml.safe_load``（不执行任意对象），失败抛 :class:`ExamConfigError`。

题型规范（``questions`` 为 ``题目id -> 题目`` 的映射）：

====  =============================  =============================================
键    说明                            要求
====  =============================  =============================================
type  single_choice / multiple_choice 必填
      / fill_blank / subjective
      （subjective 为主观题：文本作答、
        无选项、恒不计分）
subject  题目文本                     必填
image 题目附图（URL 或路径）          可选
score 分值，>= 0（可为 0）            必填（主观题仍可展示分值，但不计入得分）
subjective 是否主观题（不计分）       可选，默认 false（对主观题题型无意义）
options  选项映射 {a: {text/image}}   选择题必填
answer 标准答案（单选 str / 多选 list 可选（用于自动判分；主观题忽略）
      / 填空 list[可接受答案]）
allow_upload 是否允许上传文件（图片） 可选，默认 false（仅 fill_blank 有意义）
====  =============================  =============================================

顶部 ``total_score`` 为试卷总分（整数 >= 0，页首展示）。

注意：YAML 中 URL 若包含 ``#`` 需加引号。
"""

from pathlib import Path

import yaml

EXAM_FILE = Path(__file__).resolve().parent / "exam.yml"

VALID_TYPES = ("single_choice", "multiple_choice", "fill_blank", "subjective")


class ExamConfigError(ValueError):
    """exam.yml 解析或校验失败。"""


def parse_exam_yaml(text: str) -> dict:
    """用 PyYAML 解析 YAML 文本；顶层必须是映射。"""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ExamConfigError(f"exam.yml 解析失败: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ExamConfigError("exam.yml 顶层必须是映射（键值结构）")
    return data


# ---------------------------------------------------------------------------
# 规范校验
# ---------------------------------------------------------------------------

def _validate_question(qid: int, q: dict) -> None:
    if not isinstance(q, dict):
        raise ExamConfigError(f"题目 {qid} 必须是字典")
    qtype = q.get("type")
    if qtype not in VALID_TYPES:
        raise ExamConfigError(
            f"题目 {qid} 的 type 不合法（应为 {'/'.join(VALID_TYPES)}）: {qtype!r}"
        )
    subject = q.get("subject")
    if not isinstance(subject, str) or not subject.strip():
        raise ExamConfigError(f"题目 {qid} 缺少 subject")
    score = q.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool) or score < 0:
        raise ExamConfigError(f"题目 {qid} 的 score 必须为 >= 0 的数字")
    if q.get("subjective") is not None and not isinstance(q.get("subjective"), bool):
        raise ExamConfigError(f"题目 {qid} 的 subjective 必须为布尔值")

    options = q.get("options")
    if qtype in ("single_choice", "multiple_choice"):
        if not isinstance(options, dict) or not options:
            raise ExamConfigError(f"题目 {qid} 为选择题但缺少 options")
        for key, opt in options.items():
            if not isinstance(opt, dict) or not (opt.get("text") or opt.get("image")):
                raise ExamConfigError(f"题目 {qid} 的选项 {key!r} 必须包含 text 或 image")
        answer = q.get("answer")
        if qtype == "single_choice":
            if answer is not None and (not isinstance(answer, str) or answer not in options):
                raise ExamConfigError(f"题目 {qid} 的 answer 必须是某个选项键")
        else:
            if answer is not None:
                if not isinstance(answer, list) or not all(
                    isinstance(x, str) and x in options for x in answer
                ):
                    raise ExamConfigError(f"题目 {qid} 的 answer 必须是选项键列表")
    elif qtype == "fill_blank":
        answer = q.get("answer")
        if answer is not None:
            if not isinstance(answer, list) or not answer:
                raise ExamConfigError(f"题目 {qid}（填空题）的 answer 必须为非空的可接受答案列表")
            first = answer[0]
            if isinstance(first, str):
                # 单项填空：多个可接受答案 ["a", "b"]
                if not all(isinstance(x, str) for x in answer):
                    raise ExamConfigError(f"题目 {qid}（填空题）的 answer 元素必须为字符串")
            elif isinstance(first, list):
                # 多项填空：每空一组可接受答案 [["a"], ["b"]]
                for blank in answer:
                    if not isinstance(blank, list) or not blank or not all(
                        isinstance(x, str) for x in blank
                    ):
                        raise ExamConfigError(
                            f"题目 {qid}（多项填空）每空的答案必须为非空的字符串列表"
                        )
            else:
                raise ExamConfigError(f"题目 {qid}（填空题）的 answer 格式不合法")
        allow_upload = q.get("allow_upload")
        if allow_upload is not None and not isinstance(allow_upload, bool):
            raise ExamConfigError(f"题目 {qid} 的 allow_upload 必须为布尔值")
    else:  # subjective 主观题：文本作答，无选项，不计分
        answer = q.get("answer")
        if answer is not None and not isinstance(answer, str):
            raise ExamConfigError(f"题目 {qid}（主观题）的 answer 必须为字符串（如有）")
    image = q.get("image")
    if image is not None and not isinstance(image, str):
        raise ExamConfigError(f"题目 {qid} 的 image 必须为字符串")
    images = q.get("images")
    if images is not None and (
        not isinstance(images, list) or not all(isinstance(x, str) for x in images)
    ):
        raise ExamConfigError(f"题目 {qid} 的 images 必须为字符串列表（多张附图）")


def fill_blank_blanks(answer) -> list[list[str]]:
    """规范化填空题答案：返回「每空的可接受答案列表」。

    单项填空 ``["a", "b"]``（一个空、多个可接受答案）→ ``[["a", "b"]]``；
    多项填空 ``[["a"], ["b"]]``（多个空）→ 原样返回。
    """
    if not answer:
        return []
    if isinstance(answer[0], str):
        return [[str(a) for a in answer]]
    return [[str(x) for x in blank] for blank in answer]


def validate_exam_dict(data: dict) -> dict:
    """校验并规范化试卷字典（与 load_exam_config 同一套校验）。

    成功返回 ``{"total_score": int, "questions": {qid: {...}}, "tips": str}``；
    失败抛 :class:`ExamConfigError`。
    """
    total = data.get("total_score")
    if not isinstance(total, (int, float)) or isinstance(total, bool) or total < 0:
        raise ExamConfigError("total_score 必须为 >= 0 的数字")
    questions = data.get("questions")
    if not isinstance(questions, dict) or not questions:
        raise ExamConfigError("questions 必须为非空映射")
    tips = data.get("tips")
    if tips is not None and not isinstance(tips, str):
        raise ExamConfigError("tips 必须为字符串（试卷说明，支持 Markdown）")
    tips_doc = data.get("tips_doc")
    if tips_doc is not None and not isinstance(tips_doc, str):
        raise ExamConfigError("tips_doc 必须为字符串（试卷说明文档地址）")
    result = {}
    for key, q in questions.items():
        try:
            qid = int(key)
        except (TypeError, ValueError):
            raise ExamConfigError(f"题目 id 必须为整数: {key!r}") from None
        _validate_question(qid, q)
        q = dict(q)
        # 主观题 / 标记"不计分"的题目恒 0 分：分值规范化为 0（展示与判分一致，
        # 避免管理员为这类题目设置无意义的分值）
        if q.get("subjective") or q.get("type") == "subjective":
            q["score"] = 0
        # 附图统一为 images 列表（兼容旧的单个 image 字段：并入列表后移除）
        imgs = [i for i in (q.get("images") or []) if isinstance(i, str) and i.strip()]
        if q.get("image"):
            old = q["image"].strip()
            if old and old not in imgs:
                imgs.insert(0, old)
        if imgs:
            q["images"] = imgs
        else:
            q.pop("images", None)
        q.pop("image", None)
        result[qid] = q
    return {
        "total_score": int(total),
        "questions": result,
        "tips": tips or "",
        "tips_doc": tips_doc or "",
    }


def save_exam_config(data: dict, path: str | Path = EXAM_FILE) -> dict:
    """校验试卷配置并写回 exam.yml；成功返回规范化结构。

    供管理员在线编辑试卷使用：先校验（防止写入非法配置），
    再序列化为 YAML 覆盖写入。
    """
    validated = validate_exam_dict(data)
    config_path = Path(path)
    header = (
        "# ============================================================\n"
        "# 望海服务器二周目审核问卷（由管理员在线编辑生成）\n"
        "# 题型：single_choice / multiple_choice / fill_blank / subjective\n"
        "# ============================================================\n"
    )
    dump = {
        "total_score": validated["total_score"],
        "questions": validated["questions"],
    }
    if validated.get("tips"):
        dump["tips"] = validated["tips"]
    if validated.get("tips_doc"):
        dump["tips_doc"] = validated["tips_doc"]
    text = header + yaml.safe_dump(
        dump,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    try:
        config_path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise ExamConfigError(f"无法写入考试配置 {config_path}: {exc}") from exc
    return validated


def load_exam_config(path: str | Path = EXAM_FILE) -> dict:
    """读取并校验 exam.yml，返回规范结构：
    ``{"total_score": int, "questions": {qid: {...}}}``
    """
    config_path = Path(path)
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ExamConfigError(f"无法读取考试配置 {config_path}: {exc}") from exc
    return validate_exam_dict(parse_exam_yaml(text))
