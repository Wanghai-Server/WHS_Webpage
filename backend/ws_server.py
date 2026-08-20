"""后端 WS 命令服务：与 MCDR 插件（mcdr2web）双向通信。

- 仅监听环回地址 127.0.0.1:<ws_port>（端口来自 data/config.json 的 ws_port），
  标准 ws 协议、无鉴权，避免对公网暴露。
- 统一消息格式（JSON）：
    请求:  {"request_id": <str>, "command": <str>, "data": <可选>}
    响应:  {"request_id": <str>, "success": <bool>, "data": <可选>}
  - 客户端(MCDR) -> 服务端：服务端执行指令并回复 success（data 放结果）；
  - 服务端 -> 客户端：服务端发送请求，客户端执行后回复返回体（data）。
- 指令处理器通过 @server.register("指令名") 注册：async handler(data) -> 返回体。
- 服务端主动请求用 server.request("指令", data) 等待客户端响应。
"""
import asyncio
import json
import uuid

import websockets


class WsCommandServer:
    """独立 WS 命令服务（在 FastAPI lifespan 中启动/停止）。"""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._router: dict[str, callable] = {}
        self._connections: set = set()
        self._pending: dict[str, asyncio.Future] = {}
        self._server = None
        # 内置测试指令
        self.register("ping")(self._handle_ping)

    # ------------------------------------------------------------------
    # 指令注册
    # ------------------------------------------------------------------
    def register(self, command: str):
        """注册服务端指令处理器（处理客户端发来的请求）。

        :param command: 指令名。
        处理器签名：``async def handler(data) -> Any``，返回值写入响应 data；
        处理器抛出的异常会被转换为 ``success=False`` 的响应。
        """
        def decorator(func):
            self._router[command] = func
            return func
        return decorator

    async def _handle_ping(self, data):
        return "pong"

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """启动监听（调用后开始接受连接）。"""
        self._server = await websockets.serve(
            self._handle_connection, self.host, self.port
        )
        print(f"[ws-server] 监听 ws://{self.host}:{self.port}", flush=True)

    async def stop(self) -> None:
        """关闭服务并等待监听结束。"""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            print("[ws-server] 已停止", flush=True)

    async def wait_until_closed(self) -> None:
        """阻塞直到服务关闭（供 lifespan 中的常驻任务持有）。"""
        if self._server is not None:
            await self._server.wait_closed()

    # ------------------------------------------------------------------
    # 连接处理
    # ------------------------------------------------------------------
    async def _handle_connection(self, ws):
        self._connections.add(ws)
        print(f"[ws-server] 客户端已连接（当前 {len(self._connections)}）", flush=True)
        try:
            async for raw in ws:
                await self._handle_message(ws, raw)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as exc:
            print(f"[ws-server] 连接异常: {type(exc).__name__}: {exc}", flush=True)
        finally:
            self._connections.discard(ws)
            print(f"[ws-server] 客户端断开（剩余 {len(self._connections)}）", flush=True)

    async def _handle_message(self, ws, raw: str) -> None:
        """处理一条客户端消息：要么是客户端请求，要么是对服务端请求的响应。"""
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            print(f"[ws-server] 收到非法消息: {str(raw)[:200]!r}", flush=True)
            return
        request_id = payload.get("request_id")
        if "success" in payload:
            # 对服务端主动请求的响应：交给等待中的 future
            future = self._pending.pop(request_id, None)
            if future is not None and not future.done():
                future.set_result(payload)
            return
        command = payload.get("command")
        if not request_id or not command:
            return
        handler = self._router.get(command)
        try:
            if handler is None:
                raise ValueError(f"未知指令: {command}")
            result = await handler(payload.get("data"))
            await ws.send(json.dumps({
                "request_id": request_id,
                "success": True,
                "data": result,
            }, ensure_ascii=False))
        except Exception as exc:
            print(
                f"[ws-server] 指令 {command} 执行失败: {type(exc).__name__}: {exc}",
                flush=True,
            )
            try:
                await ws.send(json.dumps({
                    "request_id": request_id,
                    "success": False,
                    "data": str(exc),
                }, ensure_ascii=False))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 服务端主动请求（等待客户端返回返回体）
    # ------------------------------------------------------------------
    async def request(self, command: str, data=None, timeout: float = 10.0) -> dict:
        """向已连接的客户端发送请求，等待其响应，返回完整响应 dict。

        :raises ConnectionError: 无已连接的客户端。
        :raises asyncio.TimeoutError: 超时未收到响应。
        """
        if not self._connections:
            raise ConnectionError("无已连接的 MCDR 客户端")
        request_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[request_id] = future
        message = json.dumps({
            "request_id": request_id,
            "command": command,
            "data": data,
        }, ensure_ascii=False)
        try:
            # 广播给所有已连接客户端（首个响应的胜出，便于未来多实例）
            for ws in list(self._connections):
                try:
                    await ws.send(message)
                except Exception:
                    self._connections.discard(ws)
            return await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(request_id, None)
