"""全量搜索路由：wiki 页面 + 用户 + 反馈。

``GET /api/search?q=&lang=`` 为公开接口：
- ``wiki``：复用维基搜索（FTS5 全文索引 + LIKE 兜底，按语言）；
- ``users``：用户公开信息搜索（users 表 JOIN user_info 表）；
- ``feedback``：反馈标题 / 正文搜索（附带作者名称与命中摘要）。
"""
from fastapi import APIRouter

from data.main.database.wiki_database import LANGS
from main import feedback_db, user_db, wiki_db

router = APIRouter()


def _normalize_lang(lang: str) -> str:
    lang = (lang or "zh").strip().lower()
    return lang if lang in LANGS else "zh"


def _author_name(uid: int) -> str:
    """把 uid 解析为展示名称（昵称优先，其次用户名）。"""
    if not uid:
        return ""
    user = user_db.get_user(uid=uid)
    if not user:
        return ""
    return user.get("fullname") or user.get("username") or ""


@router.get("/api/search")
def full_search(q: str = "", lang: str = "zh"):
    """按关键词全量搜索：wiki 页面（按语言）+ 用户公开信息 + 反馈。"""
    lang = _normalize_lang(lang)
    query = (q or "").strip()[:100]
    if not query:
        return {"query": "", "lang": lang, "wiki": [], "users": [], "feedback": []}
    wiki_results = wiki_db.search_pages(query, lang=lang, limit=20)
    users = user_db.search_users(query, limit=20)
    feedback_results = feedback_db.search_feedbacks(query, limit=20)
    for item in feedback_results:
        item["author_name"] = _author_name(item.get("author_uid"))
    return {
        "query": query,
        "lang": lang,
        "wiki": wiki_results,
        "users": users,
        "feedback": feedback_results,
    }
