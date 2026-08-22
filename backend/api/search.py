"""全量搜索路由：wiki 页面 + 用户（用户名 / uid / 昵称 / 玩家名 / 小号名）。

``GET /api/search?q=&lang=`` 为公开接口：
- ``wiki``：复用维基搜索（FTS5 全文索引 + LIKE 兜底，按语言）；
- ``users``：用户公开信息搜索（users 表 JOIN user_info 表）。
"""
from fastapi import APIRouter

from data.main.database.wiki_database import LANGS
from main import user_db, wiki_db

router = APIRouter()


def _normalize_lang(lang: str) -> str:
    lang = (lang or "zh").strip().lower()
    return lang if lang in LANGS else "zh"


@router.get("/api/search")
def full_search(q: str = "", lang: str = "zh"):
    """按关键词全量搜索：wiki 页面（按语言）+ 用户公开信息。"""
    lang = _normalize_lang(lang)
    query = (q or "").strip()[:100]
    if not query:
        return {"query": "", "lang": lang, "wiki": [], "users": []}
    wiki_results = wiki_db.search_pages(query, lang=lang, limit=20)
    users = user_db.search_users(query, limit=20)
    return {"query": query, "lang": lang, "wiki": wiki_results, "users": users}
