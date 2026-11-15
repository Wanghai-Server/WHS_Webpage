"""在线地图路由：代理 BlueMap 的瓦片 / 实时玩家数据。

设计要点：
- 瓦片由 BlueMap 渲染（磁盘上为 gzip 压缩的 PNG），浏览器无法直接跨端口访问，
  因此统一经后端代理，顺带做成员鉴权与缓存。
- 前端加载瓦片用的是 <img>，带不了 Authorization 头，所以瓦片走**短期签名 URL**：
  /api/map/config 下发带 uid + 过期时间 + HMAC 签名的地址，过期后前端重新取一次。
- 仅限正式成员（permission >= 2，即通过入服问卷）访问。
"""
import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse, Response

from data import read_config
from main import _token_secret, get_current_user

router = APIRouter()

# 瓦片签名有效期（秒）；前端在过期前 60 秒自动续签
SIGN_TTL = 600
# 瓦片可被浏览器 / CDN 缓存的时间（秒）
TILE_CACHE_TTL = 86400
# 正式成员门槛：permission >= 2 等价于已通过入服问卷
MEMBER_PERMISSION = 2


def _map_cfg() -> dict:
    """读取 config.json 的 map 段；缺省时指向 BlueMap 公共演示服，便于本地先跑通链路。"""
    cfg = read_config().get("map", {}) or {}
    maps = cfg.get("maps") or ["overworld_2d"]
    if isinstance(maps, str):
        maps = [maps]
    maps = [str(m) for m in maps]
    return {
        "base": str(cfg.get("bluemap_base") or "https://bluecolored.de/bluemap").rstrip("/"),
        "maps": maps,
        "default": str(cfg.get("default") or maps[0]),
        "timeout": float(cfg.get("timeout") or 10),
        "center": cfg.get("center") or [0, 0],
        "zoom": cfg.get("zoom", -2),
    }


def _error(code: str, status: int, zh: str, en: str) -> JSONResponse:
    """与全站一致的结构化双语错误响应。"""
    return JSONResponse(status_code=status, content={"code": code, "message": {"zh": zh, "en": en}})


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _tile_token(uid: int, map_id: str, exp: int) -> str:
    """签发瓦片访问令牌：base64(uid:exp).base64(HMAC)，有效期由 exp 控制。"""
    mac = hmac.new(_token_secret().encode(), f"{uid}:{map_id}:{exp}".encode(), hashlib.sha256).digest()
    return f"{_b64(f'{uid}:{exp}'.encode())}.{_b64(mac)}"


def _verify_tile_token(token: str, map_id: str) -> bool:
    """校验瓦片访问令牌：格式、有效期、签名（签名绑定了 map_id，防止换图重放）。"""
    try:
        payload, mac = token.split(".")
        uid, exp = _unb64(payload).decode().split(":")
        uid, exp = int(uid), int(exp)
        given = _unb64(mac)
    except Exception:
        return False
    if exp < int(time.time()):
        return False
    expect = hmac.new(_token_secret().encode(), f"{uid}:{map_id}:{exp}".encode(), hashlib.sha256).digest()
    return hmac.compare_digest(given, expect)


def _member(authorization: str):
    """返回 (user, None) 或 (None, 错误响应)。"""
    user = get_current_user(authorization)
    if user is None:
        return None, _error("unauthorized", 401, "未登录或登录已过期", "Unauthorized")
    if int(user.get("permission") or 0) < MEMBER_PERMISSION:
        return None, _error(
            "map_members_only",
            403,
            "在线地图仅对正式成员开放",
            "The live map is available to members only",
        )
    return user, None


def _fetch(url: str, timeout: float) -> bytes | None:
    """拉取上游资源；404 / 连接失败返回 None。"""
    req = urllib.request.Request(url, headers={"User-Agent": "WHS-Map-Proxy/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def _map_settings(cfg: dict, mid: str) -> dict | None:
    """取 BlueMap 的 settings.json，抽出前端算瓦片坐标需要的参数。"""
    body = _fetch(f"{cfg['base']}/maps/{mid}/settings.json", cfg["timeout"])
    if body is None:
        return None
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        return None
    hires = data.get("hires") or {}
    lowres = data.get("lowres") or {}
    return {
        "name": data.get("name") or mid,
        "startPos": data.get("startPos") or [0, 0],
        "hires": {
            "tileSize": (hires.get("tileSize") or [32, 32])[0],
            "scale": (hires.get("scale") or [1, 1])[0],
            "translate": (hires.get("translate") or [0, 0])[0],
        },
        "lowres": {
            "tileSize": (lowres.get("tileSize") or [500, 500])[0],
            "lodFactor": lowres.get("lodFactor") or 5,
            "lodCount": lowres.get("lodCount") or 0,
        },
    }


@router.get("/api/map/config")
def map_config(authorization: str = Header(None)):
    """下发地图列表与带签名的瓦片地址前缀（仅正式成员）。"""
    user, err = _member(authorization)
    if err:
        return err

    cfg = _map_cfg()
    uid = int(user["uid"])
    exp = int(time.time()) + SIGN_TTL
    maps = []
    for mid in cfg["maps"]:
        maps.append({
            "id": mid,
            "tile": f"/api/map/tiles/{mid}/{{lod}}/{{x}}/{{y}}.png?t={_tile_token(uid, mid, exp)}",
            "settings": _map_settings(cfg, mid),
        })
    return {
        "maps": maps,
        "default": cfg["default"],
        "center": cfg["center"],
        "zoom": cfg["zoom"],
        "expires_at": exp,
        "refetch_after": SIGN_TTL - 60,
    }


@router.get("/api/map/tiles/{map_id}/{lod}/{x}/{y}.png")
def map_tile(map_id: str, lod: str, x: str, y: str, t: str = ""):
    """瓦片代理：校验访问令牌后透传 BlueMap 的 tiles/<lod>/<x>/<y>.png。

    BlueMap 磁盘上的瓦片是 gzip 压缩的 PNG，这里原样透传并补 Content-Encoding，
    避免后端解压后再被网关二次压缩。
    """
    if not _verify_tile_token(t, map_id):
        return _error("map_url_invalid", 403, "地图地址无效或已过期", "Invalid or expired map URL")

    cfg = _map_cfg()
    if map_id not in cfg["maps"]:
        return _error("map_not_found", 404, "地图不存在", "Map not found")
    if not all(part.lstrip("-").isdigit() for part in (lod, x, y)):
        return _error("invalid_parameter", 400, "请求参数不合法", "Invalid request parameters")

    body = _fetch(f"{cfg['base']}/maps/{map_id}/tiles/{lod}/{x}/{y}.png", cfg["timeout"])
    if body is None:
        # 不存在或上游异常：返回 404 让 Leaflet 安静跳过该瓦片
        return Response(status_code=404)

    headers = {"Cache-Control": f"public, max-age={TILE_CACHE_TTL}"}
    if body[:2] == b"\x1f\x8b":
        headers["Content-Encoding"] = "gzip"
    return Response(content=body, media_type="image/png", headers=headers)


@router.get("/api/map/players")
def map_players(map_id: str = "", authorization: str = Header(None)):
    """在线玩家位置（BlueMap live 接口透传；前端轮询，带 Authorization 头）。"""
    user, err = _member(authorization)
    if err:
        return err

    cfg = _map_cfg()
    mid = map_id or cfg["default"]
    if mid not in cfg["maps"]:
        return _error("map_not_found", 404, "地图不存在", "Map not found")

    body = _fetch(f"{cfg['base']}/maps/{mid}/live/players.json", cfg["timeout"])
    if body is None:
        return _error("map_upstream_error", 502, "地图服务暂时不可用", "Map service unavailable")
    try:
        return JSONResponse(json.loads(body.decode("utf-8")))
    except Exception:
        return _error("map_upstream_error", 502, "地图服务返回异常", "Map service returned invalid data")
