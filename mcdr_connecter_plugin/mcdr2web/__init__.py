import asyncio
import concurrent.futures
import json
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional

import websockets
from websockets.asyncio.client import ClientConnection

from mcdreforged.api.all import *

from whitelist_api import get_whitelist, add_player, remove_player
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
}
RECONNECT_DELAY = 5.0
REQUEST_TIMEOUT = 10.0

server_interface: Optional[PluginServerInterface] = None
config: Dict[str, Any] = {}
send_queue: Optional[asyncio.Queue[dict]] = None
pending: Dict[str, asyncio.Future] = {}
connected: bool = False
main_loop_future: Optional[concurrent.futures.Future] = None

async def _handle_ping(data: Any) -> str:
    return "pong"


command_handlers: Dict[str, Callable[[Any], Awaitable[Any]]] = {
    "ping": _handle_ping,
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
    global server_interface, config, send_queue, main_loop_future
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


def on_unload(server: PluginServerInterface) -> None:
    global main_loop_future
    if main_loop_future is not None:
        main_loop_future.cancel()
        main_loop_future = None
    server.logger.info(f"[{PLUGIN_ID}] 已卸载")
