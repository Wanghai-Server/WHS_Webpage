"""服务器实时状态路由。"""
import datetime
import time

from fastapi import APIRouter

from main import (
    SERVER_STATUS_TTL,
    _SERVER_STATUS_CACHE,
    _SERVER_STATUS_LOCK,
    _fetch_server_status,
)

router = APIRouter()


@router.get("/api/server/status")
def server_status():
    """服务器实时状态（公开接口，无需登录）。

    后端每 5 分钟重新探测一次并缓存结果；探测失败时返回上一次成功
    缓存（若存在），否则返回离线占位数据。
    """
    now = time.time()
    with _SERVER_STATUS_LOCK:
        cache = _SERVER_STATUS_CACHE
        if cache["data"] is not None and now - cache["fetched_at"] < SERVER_STATUS_TTL:
            return cache["data"]
        data = _fetch_server_status()
        if data is None and cache["data"] is not None:
            return cache["data"]
        if data is None:
            data = {
                "online": False,
                "version": "",
                "players": {"online": 0, "max": 0},
                "latency_ms": None,
                "tps": None,
                "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            }
        cache["data"] = data
        cache["fetched_at"] = now
        return data
