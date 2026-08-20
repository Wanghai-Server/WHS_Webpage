# -*- coding: utf-8 -*-
"""WS 命令服务双向通信测试（不依赖后端，直接驱动 WsCommandServer）。"""
import asyncio
import json
import sys

sys.path.insert(0, "backend")

from ws_server import WsCommandServer  # noqa: E402

PORT = 8799


async def mock_client():
    import websockets

    async with websockets.connect(f"ws://127.0.0.1:{PORT}") as ws:
        # 1) 客户端 -> 服务端：ping 请求
        await ws.send(json.dumps({"request_id": "c1", "command": "ping"}))
        resp = json.loads(await ws.recv())
        assert resp["request_id"] == "c1" and resp["success"] and resp["data"] == "pong"
        print("PASS 客户端->服务端: ping ->", resp["data"])

        # 2) 服务端 -> 客户端：等后端的主动请求并回复返回体
        req = json.loads(await ws.recv())
        assert req["command"] == "ping"
        await ws.send(json.dumps({"request_id": req["request_id"], "success": True, "data": "pong-from-client"}))
        print("PASS 收到服务端请求:", req["command"])

        # 3) 未知指令 -> 服务端返回 success=False
        await ws.send(json.dumps({"request_id": "c2", "command": "no_such_cmd"}))
        resp2 = json.loads(await ws.recv())
        assert resp2["request_id"] == "c2" and not resp2["success"]
        print("PASS 未知指令 -> success=False:", resp2["data"])


async def main():
    srv = WsCommandServer("127.0.0.1", PORT)
    await srv.start()
    client_task = asyncio.create_task(mock_client())
    await asyncio.sleep(0.6)  # 等客户端连上

    # 服务端 -> 客户端：主动请求（应在 mock_client 的第 2 步被应答）
    resp = await srv.request("ping", timeout=5)
    assert resp["success"] and resp["data"] == "pong-from-client"
    print("PASS 服务端->客户端: request ping ->", resp["data"])

    await client_task
    await srv.stop()
    print("ALL PASS")


asyncio.run(main())
