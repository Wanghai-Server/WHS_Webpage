"""在线地图路由：下发 BlueMap 网页入口与短期访问凭据。

2D 与 3D 都由 BlueMap 自带网页端渲染，网站不参与瓦片拼装，只做三件事：
- 校验成员身份后下发入口路径、地图列表与出生点
- 签发短期 HttpOnly Cookie，供 nginx 的 auth_request 校验反向代理请求
- 透传在线玩家数量

瓦片路径、层级、投影与出生点全交给 BlueMap 自己处理，因此不会再出现
路径语义、LOD 错位或坐标偏移的问题；2D / 3D 只是同一个网页端的不同视图。
"""
import base64
import hashlib
import hmac
import json
import time
import urllib.request

from fastapi import APIRouter, Header, Request, Response

from data import read_config
from main import _error_response, _token_secret, get_current_user

router = APIRouter()

# 正式成员门槛：permission >= 2 等价于已通过入服问卷
_MEMBER_PERMISSION = 2
# BlueMap settings.json 与入口探活的进程内缓存（秒）
_SETTINGS_TTL = 300
_PROBE_TTL = 30

_SETTINGS_CACHE: dict[str, tuple[float, dict | None]] = {}
_PROBE_CACHE: dict[str, tuple[float, bool]] = {}


def _map_cfg() -> dict:
    cfg = read_config().get("map", {}) or {}
    maps = cfg.get("maps") or ["world"]
    if isinstance(maps, str):
        maps = [maps]
    maps = [str(m) for m in maps]
    return {
        # 后端拉取 settings.json / 玩家数据用的上游地址，只在内网访问
        "base": str(cfg.get("bluemap_base") or "http://127.0.0.1:8100").rstrip("/"),
        # 浏览器访问的入口，必须是同源路径，由 nginx 反代到上面的 base
        "viewer": str(cfg.get("bluemap_viewer") or "/map3d/"),
        "maps": maps,
        "default": str(cfg.get("default") or maps[0]),
        "timeout": float(cfg.get("timeout") or 10),
        "cookie": str(cfg.get("cookie_name") or "whs_map"),
        "ttl": int(cfg.get("viewer_ttl") or 600),
        "cookie_secure": bool(cfg.get("cookie_secure", False)),
        "start_y": float(cfg.get("start_y") or 80),
    }


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(uid: int, exp: int) -> str:
    """签发地图通行凭据：base64(uid:exp).base64(HMAC)。"""
    mac = hmac.new(_token_secret().encode(), f"map:{uid}:{exp}".encode(), hashlib.sha256).digest()
    return f"{_b64(f'{uid}:{exp}'.encode())}.{_b64(mac)}"


def _verify(value: str) -> bool:
    """校验凭据的格式、有效期与签名。"""
    try:
        payload, mac = value.split(".")
        uid, exp = _unb64(payload).decode().split(":")
        int(uid), int(exp)
        given = _unb64(mac)
    except Exception:
        return False
    if int(exp) < int(time.time()):
        return False
    expect = hmac.new(_token_secret().encode(), f"map:{uid}:{exp}".encode(), hashlib.sha256).digest()
    return hmac.compare_digest(given, expect)


def _member(authorization: str):
    """返回 (user, None) 或 (None, 错误响应)。"""
    user = get_current_user(authorization)
    if user is None:
        return None, _error_response("unauthorized", 401)
    if int(user.get("permission") or 0) < _MEMBER_PERMISSION:
        return None, _error_response("map_members_only", 403)
    return user, None


def _fetch(url: str, timeout: float) -> bytes | None:
    """拉取上游资源；连接失败或非 200 返回 None。"""
    req = urllib.request.Request(url, headers={"User-Agent": "WHS-Map-Proxy/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def _viewer_alive(cfg: dict) -> bool:
    """探测 BlueMap 网页端是否已部署，避免前端 iframe 拿到 404 白屏。"""
    key = cfg["base"]
    cached = _PROBE_CACHE.get(key)
    if cached and time.time() - cached[0] < _PROBE_TTL:
        return cached[1]
    alive = _fetch(f"{key}/index.html", cfg["timeout"]) is not None
    _PROBE_CACHE[key] = (time.time(), alive)
    return alive


def _map_meta(cfg: dict, mid: str) -> dict | None:
    """取 BlueMap 的 settings.json（带进程内缓存），只需要名字与出生点。"""
    key = f"{cfg['base']}|{mid}"
    cached = _SETTINGS_CACHE.get(key)
    if cached and time.time() - cached[0] < _SETTINGS_TTL:
        return cached[1]
    body = _fetch(f"{cfg['base']}/maps/{mid}/settings.json", cfg["timeout"])
    meta = None
    if body:
        try:
            data = json.loads(body.decode("utf-8"))
            start = data.get("startPos") or [0, 0]
            meta = {
                "name": data.get("name") or mid,
                "start": [int(start[0]), int(start[1])],
            }
        except Exception:
            meta = None
    _SETTINGS_CACHE[key] = (time.time(), meta)
    return meta


@router.get("/api/map/config")
def map_config(response: Response, authorization: str = Header(None)):
    """下发入口配置，并写入短期 HttpOnly Cookie。"""
    user, err = _member(authorization)
    if err:
        return err

    cfg = _map_cfg()
    if not _viewer_alive(cfg):
        return _error_response("map_not_ready", 503)

    exp = int(time.time()) + cfg["ttl"]
    response.set_cookie(
        key=cfg["cookie"],
        value=_sign(int(user["uid"]), exp),
        max_age=cfg["ttl"],
        path="/",
        httponly=True,
        samesite="lax",
        secure=cfg["cookie_secure"],
    )

    items = []
    for mid in cfg["maps"]:
        meta = _map_meta(cfg, mid) or {}
        items.append({
            "id": mid,
            "name": meta.get("name") or mid,
            "start": meta.get("start") or [0, 0],
        })
    return {
        "viewer": cfg["viewer"],
        "maps": items,
        "default": cfg["default"],
        "start_y": cfg["start_y"],
        "ttl": cfg["ttl"],
    }


@router.get("/api/map/auth")
def map_auth(request: Request):
    """供 nginx 的 auth_request 调用：只校验 Cookie，不返回业务数据。"""
    value = request.cookies.get(_map_cfg()["cookie"])
    if value and _verify(value):
        return Response(status_code=204)
    return Response(status_code=401)


@router.get("/api/map/players")
def map_players(map_id: str = "", authorization: str = Header(None)):
    """当前世界的在线玩家数量（页头展示用）。"""
    _, err = _member(authorization)
    if err:
        return err

    cfg = _map_cfg()
    mid = map_id or cfg["default"]
    if mid not in cfg["maps"]:
        return _error_response("map_not_found", 404)

    body = _fetch(f"{cfg['base']}/maps/{mid}/live/players.json", cfg["timeout"])
    if body is None:
        return _error_response("map_upstream_error", 502)
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        return _error_response("map_upstream_error", 502)

    players = data.get("players") or []
    # foreign 表示玩家在其他维度（hide-different-world: false 时会出现），不计入当前世界
    return {"count": sum(1 for p in players if not p.get("foreign"))}
