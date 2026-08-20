import asyncio
import concurrent.futures
import json
import re
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional

import websockets
from websockets.asyncio.client import ClientConnection

from mcdreforged.api.all import *

from whitelist_api import get_whitelist_names, add_player, remove_player
from online_player_api import get_player_list, is_online

PLUGIN_METADATA = {
    "id": "mcdr2web",
    "version": "1.0.0",
    "name": "MCDR to Web",
    "description": {
        "zh_cn": "将 Minecraft 服务器（MCDReforged）与望海官网打通：上报服务器状态与在线玩家，同步白名单。",
        "en_us": "Bridges the Minecraft server (MCDReforged) with the WangHai website: reports server status and online players, and syncs the whitelist."
    },
    "dependencies": {
        "mcdreforged": ">=2.15.0",
        "whitelist_api": ">=2.0.0",
        "online_player_api": ">=1.0.0"
    }
}

PLUGIN_ID = "mcdr2web"
CONFIG_FILE = "mcdr2web.json"
DEFAULT_CONFIG: Dict[str, Any] = {
    "ws_host": "127.0.0.1",
    "ws_port": 8765,
    # TPS/MSPT 主动上报间隔（秒）：通过 RCON 执行 `tick query` 采集后上报后端
    "tps_report_interval": 300,
}
RECONNECT_DELAY = 5.0
REQUEST_TIMEOUT = 10.0

server_interface: Optional[PluginServerInterface] = None
config: Dict[str, Any] = {}
send_queue: Optional[asyncio.Queue[dict]] = None
pending: Dict[str, asyncio.Future] = {}
connected: bool = False
main_loop_future: Optional[concurrent.futures.Future] = None
tps_loop_future: Optional[concurrent.futures.Future] = None

async def _handle_ping(data: Any) -> str:
    return "pong"


async def _handle_get_player_list(data: Any) -> Any:
    """获取当前在线玩家名单（直接返回名单本身，由后端区分假人/真人）。"""
    return await asyncio.to_thread(get_player_list)


async def _handle_is_online(data: Any) -> Any:
    """判断某个玩家是否在线（大小写不敏感）。"""
    player = str((data or {}).get("player") or "") if isinstance(data, dict) else str(data or "")
    if not player:
        raise ValueError("缺少 player 参数")
    return await asyncio.to_thread(is_online, player, False)


async def _handle_get_whitelist(data: Any) -> Any:
    """获取白名单列表（返回玩家名列表）。"""
    return await asyncio.to_thread(get_whitelist_names)


async def _handle_add_player(data: Any) -> Any:
    """把玩家加入白名单（正版/离线模式由 whitelist_api 自动适配）。"""
    player = str((data or {}).get("player") or "") if isinstance(data, dict) else str(data or "")
    if not player:
        raise ValueError("缺少 player 参数")
    await asyncio.to_thread(add_player, player)
    return True


async def _handle_remove_player(data: Any) -> Any:
    """从白名单移除玩家。"""
    player = str((data or {}).get("player") or "") if isinstance(data, dict) else str(data or "")
    if not player:
        raise ValueError("缺少 player 参数")
    await asyncio.to_thread(remove_player, player)
    return True


command_handlers: Dict[str, Callable[[Any], Awaitable[Any]]] = {
    "ping": _handle_ping,
    # 在线名单 / 在线判断（whs 官网在线人数只统计真人，bot_ 前缀视为假人）
    "get_player_list": _handle_get_player_list,
    "is_online": _handle_is_online,
    # 白名单（考试通过自动加、封禁/注销小号自动移；列表为关于页成员墙预留）
    "get_whitelist": _handle_get_whitelist,
    "add_player": _handle_add_player,
    "remove_player": _handle_remove_player,
}

async def _main_loop() -> None:
    global connected
    url = f"ws://{config['ws_host']}:{config['ws_port']}"
    while True:
        try:
            server_interface.logger.info(f"[{PLUGIN_ID}] 正在连接后端 WS 服务 {url} ...")
            async with websockets.connect(url) as conn:
                connected = True
                server_interface.logger.info(f"[{PLUGIN_ID}] 已连接后端 WS 服务")
                try:
                    await asyncio.gather(_recv_loop(conn), _send_loop(conn))
                except Exception as exc:
                    server_interface.logger.warning(f"[{PLUGIN_ID}] WS 会话异常: {exc}")
        except Exception as exc:
            server_interface.logger.warning(f"[{PLUGIN_ID}] WS 连接失败: {exc}")
        finally:
            connected = False
        await asyncio.sleep(RECONNECT_DELAY)


async def _send_loop(conn: ClientConnection) -> None:
    """单写者发送循环：从队列取消息发送；发送失败时放回队列并中断会话（触发重连重发）。"""
    while True:
        msg = await send_queue.get()
        try:
            await conn.send(json.dumps(msg, ensure_ascii=False))
        except Exception as exc:
            await send_queue.put(msg)
            raise exc


async def _recv_loop(conn: ClientConnection) -> None:
    """接收循环：区分"后端对我们请求的响应"（含 success）与"后端发来的请求"（含 command）。"""
    async for raw in conn:
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            server_interface.logger.warning(f"[{PLUGIN_ID}] 收到非法消息: {str(raw)[:200]}")
            continue
        request_id = payload.get("request_id")
        if "success" in payload:
            # 后端对我们请求的响应
            future = pending.pop(request_id, None)
            if future is not None and not future.done():
                future.set_result(payload)
            continue
        # 后端发来的请求：执行指令并回复返回体
        command = payload.get("command")
        handler = command_handlers.get(command)
        try:
            if handler is None:
                raise ValueError(f"未知指令: {command}")
            result = await handler(payload.get("data"))
            await send_queue.put({
                "request_id": request_id,
                "success": True,
                "data": result,
            })
        except Exception as exc:
            server_interface.logger.warning(f"[{PLUGIN_ID}] 指令 {command} 执行失败: {exc}")
            await send_queue.put({
                "request_id": request_id,
                "success": False,
                "data": str(exc),
            })


async def send_message(msg: dict) -> None:
    """异步发送一条消息（进入发送队列）。"""
    await send_queue.put(msg)


async def request_async(command: str, data: Any = None, timeout: float = REQUEST_TIMEOUT) -> dict:
    """插件 -> 后端：发送请求并等待响应，返回完整响应 dict。"""
    request_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    pending[request_id] = future
    try:
        await send_message({"request_id": request_id, "command": command, "data": data})
        return await asyncio.wait_for(future, timeout)
    finally:
        pending.pop(request_id, None)


def request_sync(command: str, data: Any = None, timeout: float = REQUEST_TIMEOUT) -> dict:
    """同步版请求（供聊天指令等同步上下文调用）。未连接时直接返回失败。"""
    if not connected:
        return {"success": False, "data": "未连接后端 WS 服务"}
    return asyncio.run_coroutine_threadsafe(
        request_async(command, data, timeout), server_interface.get_loop()
    ).result(timeout + 1)


# ---------------------------------------------------------------------------
# TPS / MSPT 周期上报（RCON `tick query`，默认每 5 分钟主动上报一次后端）
# ---------------------------------------------------------------------------

def parse_tick_query_output(text: str) -> Optional[Dict[str, Any]]:
    """解析 Minecraft `tick query` 输出，返回 {"tps", "mspt", "healthy"}；解析失败返回 None。

    输出示例（1.16.2+，RCON 返回多行文本）：
      [Server] [19:07:59] [Server thread/INFO]: The game is running normally
      [Server] [19:07:59] [Server thread/INFO]: Target tick rate: 20.0 per second.
      [Server] Average time per tick: 23.4ms (Target: 50.0ms)
      [Server] [19:07:59] [Server thread/INFO]: Percentiles: P50: 22.9ms P95: 36.4ms P99: 41.9ms. Sample: 100

    TPS 由 MSPT 推导：TPS = min(目标tick率, 1000 / MSPT)（MSPT <= 50ms 时满 20）。
    """
    if not text:
        return None
    mspt_match = re.search(r"Average time per tick:\s*([0-9]+(?:\.[0-9]+)?)\s*ms", text)
    target_match = re.search(r"Target tick rate:\s*([0-9]+(?:\.[0-9]+)?)\s*per second", text)
    if mspt_match is None:
        return None
    try:
        mspt = float(mspt_match.group(1))
        target_tps = float(target_match.group(1)) if target_match else 20.0
    except ValueError:
        return None
    if mspt <= 0:
        return None
    tps = min(target_tps, 1000.0 / mspt)
    return {
        "tps": round(tps, 2),
        "mspt": round(mspt, 2),
        "healthy": "running normally" in text,
    }


def collect_tps() -> Optional[Dict[str, Any]]:
    """通过 RCON 发送 `tick query` 采集当前 TPS / MSPT；RCON 不可用或解析失败返回 None。"""
    output = server_interface.rcon_query("tick query")
    if not output:
        server_interface.logger.warning(
            f"[{PLUGIN_ID}] rcon_query('tick query') 无返回（RCON 未启用或查询失败）"
        )
        return None
    parsed = parse_tick_query_output(output)
    if parsed is None:
        server_interface.logger.warning(
            f"[{PLUGIN_ID}] tick query 输出解析失败: {str(output)[:200]}"
        )
        return None
    return parsed


def parse_list_output(text: str) -> Optional[int]:
    """解析 Minecraft `list` 命令输出中的玩家上限（max-players）。

    输出示例："There are 3 of a max of 200 players online: Steve, Alex, Notch"
    """
    if not text:
        return None
    match = re.search(r"of a max of (\d+) players online", text)
    if match is None:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def collect_max_players() -> Optional[int]:
    """通过 RCON 发送 `list` 命令获取服务器玩家上限；RCON 不可用或解析失败返回 None。"""
    output = server_interface.rcon_query("list")
    if not output:
        return None
    return parse_list_output(output)


async def report_tps_once() -> bool:
    """采集一次 TPS/MSPT（并附玩家上限）主动上报后端；WS 未连接或采集失败时跳过。返回是否成功上报。"""
    if not connected:
        return False
    stats = await asyncio.to_thread(collect_tps)
    if stats is None:
        return False
    max_players = await asyncio.to_thread(collect_max_players)
    if max_players is not None:
        stats["max"] = max_players
    try:
        resp = await request_async("report_tps", stats, timeout=REQUEST_TIMEOUT)
        return bool(resp.get("success"))
    except Exception as exc:
        server_interface.logger.warning(f"[{PLUGIN_ID}] TPS 上报失败: {exc}")
        return False


async def _tps_report_loop() -> None:
    """周期上报循环：每 tps_report_interval 秒主动上报一次 TPS/MSPT（默认 300s = 5 分钟）。"""
    interval = float(config.get("tps_report_interval") or 300)
    while True:
        try:
            await report_tps_once()
        except Exception as exc:
            server_interface.logger.warning(f"[{PLUGIN_ID}] TPS 上报循环异常: {exc}")
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# MCDR 入口 / 聊天指令
# ---------------------------------------------------------------------------
def register_commands(server: PluginServerInterface) -> None:
    builder = SimpleCommandBuilder()
    builder.command(f"!!{PLUGIN_ID} ping", cmd_ping)
    builder.command(f"!!{PLUGIN_ID} status", cmd_status)
    builder.register(server)


def cmd_ping(src: CommandSource) -> None:
    try:
        resp = request_sync("ping", timeout=5)
        if resp.get("success"):
            src.reply(RText(f"[{PLUGIN_ID}] 后端响应: {resp.get('data')}").set_color(RColor.green))
        else:
            src.reply(RText(f"[{PLUGIN_ID}] 后端返回失败: {resp.get('data')}").set_color(RColor.red))
    except Exception as exc:
        src.reply(RText(f"[{PLUGIN_ID}] 请求失败: {exc}").set_color(RColor.red))


def cmd_status(src: CommandSource) -> None:
    url = f"ws://{config['ws_host']}:{config['ws_port']}"
    src.reply(f"[{PLUGIN_ID}] 连接状态: {'已连接' if connected else '未连接'}（目标 {url}）")


def on_load(server: PluginServerInterface, prev_module: Any) -> None:
    global server_interface, config, send_queue, main_loop_future, tps_loop_future
    server_interface = server
    config = server.load_config_simple(
        CONFIG_FILE,
        default_config=DEFAULT_CONFIG,
        in_data_folder=True,
        echo_in_console=False,
    )
    send_queue = asyncio.Queue()
    register_commands(server)
    server.logger.info(
        f"[{PLUGIN_ID}] 已加载，WS 目标 ws://{config['ws_host']}:{config['ws_port']}"
    )
    main_loop_future = asyncio.run_coroutine_threadsafe(_main_loop(), server.get_loop())
    # 周期 TPS/MSPT 上报循环（RCON tick query）
    tps_loop_future = asyncio.run_coroutine_threadsafe(_tps_report_loop(), server.get_loop())


def on_unload(server: PluginServerInterface) -> None:
    global main_loop_future, tps_loop_future
    if main_loop_future is not None:
        main_loop_future.cancel()
        main_loop_future = None
    if tps_loop_future is not None:
        tps_loop_future.cancel()
        tps_loop_future = None
    server.logger.info(f"[{PLUGIN_ID}] 已卸载")
