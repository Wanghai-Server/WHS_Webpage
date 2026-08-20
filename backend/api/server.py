"""服务器实时状态路由。"""
import datetime
import time

from fastapi import APIRouter

from main import (
    SERVER_STATUS_TTL,
    _SERVER_STATUS_CACHE,
    _SERVER_STATUS_LOCK,
    _SERVER_TPS_CACHE,
    fetch_online_players,
    get_whitelist,
    is_player_online,
)

router = APIRouter()


@router.get("/api/server/status")
def server_status():
    """服务器实时状态（公开接口，无需登录）。

    数据全部来自 MCDR 插件（WS 通路）：
    - 在线状态 / 在线人数：MCDR 上报的在线名单（只统计真人，bot_ 前缀视为假人）
    - TPS / MSPT / 玩家上限：MCDR 每 5 分钟经 RCON（tick query + list）采集后主动上报
    结果缓存 5 分钟；WS 不可用时返回上一次成功缓存（若存在），否则返回离线占位数据。
    """
    now = time.time()
    with _SERVER_STATUS_LOCK:
        cache = _SERVER_STATUS_CACHE
        if cache["data"] is not None and now - cache["fetched_at"] < SERVER_STATUS_TTL:
            return cache["data"]

        # WS 在线名单：区分真人 / 假人（bot_ 前缀）
        online = fetch_online_players()
        if online is not None:
            data = {
                "online": True,
                "version": "",
                "players": {
                    "online": len(online["real"]),
                    "max": int(_SERVER_TPS_CACHE.get("max") or 0),
                },
                "latency_ms": None,
                # TPS/MSPT 来自 MCDR 周期上报（RCON tick query）；尚无上报时为 None
                "tps": _SERVER_TPS_CACHE.get("tps"),
                "mspt": _SERVER_TPS_CACHE.get("mspt"),
                # 名单明细（前端当前不用，仅预留；bots 为 bot_ 前缀假人）
                "real_players": online["real"],
                "bot_players": online["bots"],
                "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            }
        elif cache["data"] is not None:
            return cache["data"]
        else:
            data = {
                "online": False,
                "version": "",
                "players": {
                    "online": 0,
                    "max": int(_SERVER_TPS_CACHE.get("max") or 0),
                },
                "latency_ms": None,
                "tps": None,
                "mspt": None,
                "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            }
        cache["data"] = data
        cache["fetched_at"] = now
        return data


@router.get("/api/server/is_online")
def player_online(player: str = ""):
    """判断某个玩家是否在线（预留：前端暂未使用）。"""
    player = player.strip()
    if not player:
        return {"player": "", "online": False}
    return {"player": player, "online": is_player_online(player)}


@router.get("/api/server/whitelist")
def server_whitelist():
    """获取白名单列表（预留：前端暂未使用；之后作为关于页面成员墙）。"""
    return {"players": get_whitelist()}
