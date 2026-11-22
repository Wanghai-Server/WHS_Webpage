#!/usr/bin/env python3
"""后端 CI 冒烟检查（backend/）。

由 .github/workflows/ci.yml 的「后端」job 调用；也可本地直接运行：

    python .github/scripts/backend_smoke.py

检查内容：
1. backend/、data/、根目录运维脚本、MCDR 插件源码的 Python 语法编译；
2. SQLite / FTS5 能力探测（FTS5 不可用时维基搜索自动回退 LIKE，仅告警）；
3. 以随机端口真实启动 uvicorn（cwd=backend，等价于 manage.py 的启动方式），
   等待 lifespan 完成（连接全部数据库 + 启动 MCDR WS 命令服务）；
4. HTTP 接口：GET /、/api/whs、/api/user/me（401）、/api/wiki/pages、
   /api/wiki/search、未知路由（404）、错误方法（405）、工程接口（离线列表 /
   未登录 401）；
5. MCDR WS 命令服务：ping → pong、未知指令 → success=false；
6. 优雅关闭后检查日志：无 Traceback，且包含启动完成标记。

副作用：临时改写 data/config.json 的 ws_port 以避开固定端口（结束时恢复原内容）；
启动过程会在 data/ 下生成配置文件与 SQLite 数据库（均被 .gitignore 忽略）。
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_passed = 0
STARTUP_TIMEOUT = 90.0


def section(title: str) -> None:
    print(f"\n===== {title} =====", flush=True)


def ok(message: str) -> None:
    global _passed
    _passed += 1
    print(f"[PASS] {message}", flush=True)


def warn(message: str) -> None:
    print(f"::warning::{message}", flush=True)
    print(f"[WARN] {message}", flush=True)


def fail(message: str) -> None:
    print(f"::error::{message}", flush=True)
    print(f"[FAIL] {message}", flush=True)
    raise SystemExit(1)


def check(condition, message: str) -> None:
    if not condition:
        fail(message)
    ok(message)


# ---------------------------------------------------------------------------
# 语法检查 / 环境探测
# ---------------------------------------------------------------------------
def check_syntax() -> None:
    section("Python 语法")
    targets = [REPO_ROOT / "backend", REPO_ROOT / "data", REPO_ROOT / "mcdr_connecter_plugin" / "mcdr2web"]
    files: list[Path] = []
    for target in targets:
        if target.is_dir():
            files.extend(sorted(target.rglob("*.py")))
    for name in ("manage.py", "express_set_perm.py", "unlock_user.py"):
        path = REPO_ROOT / name
        if path.is_file():
            files.append(path)
    for path in files:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            fail(f"语法错误：{path.relative_to(REPO_ROOT)}: {exc}")
    ok(f"{len(files)} 个 Python 文件通过语法编译")


def probe_sqlite() -> None:
    import sqlite3

    section("SQLite 能力")
    print(f"[INFO] Python {sys.version.split()[0]} / sqlite3 {sqlite3.sqlite_version}")
    try:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE VIRTUAL TABLE ci_probe_fts USING fts5(x, tokenize='trigram')")
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        warn(f"SQLite 未启用 FTS5/trigram（{exc}）；维基搜索会自动回退 LIKE，冒烟继续。")
    else:
        ok("SQLite FTS5（trigram 分词）可用")


# ---------------------------------------------------------------------------
# 配置准备 / 端口
# ---------------------------------------------------------------------------
def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def prepare_config():
    """临时写入 config.json：ws_port 用随机端口，避免与本机/CI 其他进程冲突。

    :return: (config.json 原始内容或 None, whs_config.json 原始内容或 None,
              http_port, ws_port)
    """
    from data import read_config

    section("准备运行时配置")
    config_path = REPO_ROOT / "data" / "config.json"
    whs_config_path = REPO_ROOT / "data" / "whs_config.json"
    original = config_path.read_text(encoding="utf-8") if config_path.exists() else None
    whs_original = (
        whs_config_path.read_text(encoding="utf-8") if whs_config_path.exists() else None
    )
    config = read_config()
    if not isinstance(config, dict):
        config = {}
    http_port = free_port()
    ws_port = free_port()
    config["ws_port"] = ws_port
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
    )
    ok(f"config.json 就绪（HTTP 端口 {http_port}，MCDR WS 端口 {ws_port}）")
    return original, whs_original, http_port, ws_port


def restore_config(original, whs_original) -> None:
    """恢复运行时配置：本来没有的文件（CI / 全新克隆）直接删除。"""
    for path, content in (
        (REPO_ROOT / "data" / "config.json", original),
        (REPO_ROOT / "data" / "whs_config.json", whs_original),
    ):
        try:
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(content, encoding="utf-8")
        except OSError as exc:  # 恢复失败不应掩盖真正的检查结果
            warn(f"恢复 {path.name} 失败：{exc}")


# ---------------------------------------------------------------------------
# 启动 / 停止 uvicorn
# ---------------------------------------------------------------------------
def start_server(http_port: int):
    """启动 uvicorn，返回 (进程, 日志目录, stdout 句柄, stderr 句柄)。"""
    log_dir = Path(tempfile.mkdtemp(prefix="whs-ci-backend-"))
    stdout_path = log_dir / "uvicorn.stdout.log"
    stderr_path = log_dir / "uvicorn.stderr.log"
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    stdout_file = open(stdout_path, "w", encoding="utf-8")
    stderr_file = open(stderr_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(http_port),
            "--log-level",
            "info",
        ],
        cwd=str(REPO_ROOT / "backend"),
        stdout=stdout_file,
        stderr=stderr_file,
        env=env,
    )
    return proc, log_dir, stdout_file, stderr_file


def stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        warn("后端进程 20s 内未优雅退出，强制结束")
        proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass


def read_logs(log_dir: Path) -> str:
    parts = []
    for name in ("uvicorn.stdout.log", "uvicorn.stderr.log"):
        path = log_dir / name
        try:
            parts.append(f"----- {name} -----\n{path.read_text(encoding='utf-8', errors='replace')}")
        except OSError:
            parts.append(f"----- {name} -----\n<读取失败>")
    return "\n".join(parts)


def log_tail(text: str, lines: int = 60) -> str:
    tail = text.strip().splitlines()[-lines:]
    return "\n".join(tail)


# ---------------------------------------------------------------------------
# HTTP / WS 检查
# ---------------------------------------------------------------------------
def http_request(method: str, url: str, timeout: float = 10.0, payload=None, token: str = ""):
    """发送 HTTP 请求；支持可选 JSON 请求体与 Bearer token（供工程接口检查）。"""
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
    else:
        data = b"" if method in ("POST", "PUT", "DELETE", "PATCH") else None
        headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw) if raw.strip() else None
        except json.JSONDecodeError:
            return exc.code, raw


def wait_ready(proc: subprocess.Popen, http_port: int, log_dir: Path) -> None:
    section("启动 uvicorn")
    url = f"http://127.0.0.1:{http_port}/"
    deadline = time.monotonic() + STARTUP_TIMEOUT
    last_error = ""
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            fail(f"后端进程提前退出（exit={proc.returncode}）：\n{log_tail(read_logs(log_dir))}")
        try:
            status, _body = http_request("GET", url, timeout=2.0)
            if status == 200:
                ok(f"uvicorn 已就绪（{STARTUP_TIMEOUT:.0f}s 内）")
                return
            last_error = f"HTTP {status}"
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.3)
    fail(
        f"后端在 {STARTUP_TIMEOUT:.0f}s 内未就绪（最后错误：{last_error}）：\n"
        f"{log_tail(read_logs(log_dir))}"
    )


def check_http(base_url: str) -> None:
    section("HTTP 接口")

    status, body = http_request("GET", base_url + "/")
    check(
        status == 200
        and isinstance(body, dict)
        and body.get("message") == "Server API"
        and body.get("status") == "OK",
        "GET / 返回服务标识",
    )

    status, body = http_request("GET", base_url + "/api/whs")
    check(
        status == 200
        and isinstance(body, dict)
        and isinstance(body.get("title_suffix"), dict)
        and {"zh", "en"} <= set(body["title_suffix"])
        and isinstance(body.get("hcaptcha_site_key"), str)
        and "301" in body,
        "GET /api/whs 返回站点公开配置（title_suffix / hcaptcha_site_key / 301）",
    )

    status, body = http_request("GET", base_url + "/api/user/me")
    check(
        status == 401 and isinstance(body, dict) and body.get("code") == "unauthorized",
        "未登录 GET /api/user/me 返回 401 + code=unauthorized",
    )
    message = body.get("message") if isinstance(body, dict) else None
    check(
        isinstance(message, dict) and {"zh", "en"} <= set(message),
        "错误响应包含双语 message（zh / en）",
    )

    status, body = http_request("GET", base_url + "/api/wiki/pages")
    pages = body.get("pages") if isinstance(body, dict) else None
    check(
        status == 200
        and isinstance(pages, list)
        and any(isinstance(p, dict) and p.get("slug") == "welcome" for p in pages),
        "GET /api/wiki/pages 返回数据库播种的欢迎页",
    )

    query = urllib.parse.urlencode({"q": "欢迎", "lang": "zh"})
    status, body = http_request("GET", base_url + "/api/wiki/search?" + query)
    results = body.get("results") if isinstance(body, dict) else None
    check(
        status == 200
        and isinstance(results, list)
        and any(isinstance(r, dict) and r.get("slug") == "welcome" for r in results),
        "GET /api/wiki/search 能搜到欢迎页",
    )

    status, body = http_request("GET", base_url + "/api/ci-no-such-route")
    check(
        status == 404 and isinstance(body, dict) and body.get("code") == "not_found",
        "未知路由返回 404 + code=not_found",
    )

    status, body = http_request("GET", base_url + "/api/projects")
    check(
        status == 200
        and isinstance(body, dict)
        and body.get("online") is False
        and body.get("items") == [],
        "GET /api/projects 在 MCDR 离线时返回 200 + online=false + 空列表",
    )

    status, body = http_request(
        "POST", base_url + "/api/projects", payload={"name": "ci-project"}
    )
    check(
        status == 401 and isinstance(body, dict) and body.get("code") == "unauthorized",
        "未登录 POST /api/projects 返回 401 + code=unauthorized",
    )

    status, body = http_request("GET", base_url + "/api/projects/accounts")
    check(
        status == 401 and isinstance(body, dict) and body.get("code") == "unauthorized",
        "未登录 GET /api/projects/accounts 返回 401 + code=unauthorized",
    )

    # 轨交路线图：公开只读，不依赖 MCDR / BlueMap
    status, body = http_request("GET", base_url + "/api/map/transit")
    check(
        status == 200
        and isinstance(body, dict)
        and body.get("available") is True
        and isinstance(body.get("data", {}).get("lines"), list)
        and isinstance(body.get("data", {}).get("stations"), list)
        and isinstance(body.get("version"), str)
        and body.get("can_edit") is False,
        "GET /api/map/transit 返回线路、车站、版本号（未登录 can_edit=false）",
    )
    if isinstance(body, dict) and body.get("available"):
        data = body.get("data") or {}
        stations = {s.get("id") for s in data.get("stations") or []}
        check(
            all(sid in stations for line in data.get("lines") or [] for sid in line.get("stations") or []),
            "路线图线路引用的车站都在 stations 里",
        )
        check(
            all("y" in s and s.get("y_source") in ("explicit", "picked", "default") for s in data.get("stations") or []),
            "车站带生效的 y 与来源标记",
        )

    status, body = http_request("GET", base_url + "/api/map/transit/versions")
    check(
        status == 200
        and isinstance(body, dict)
        and isinstance(body.get("versions"), list)
        and len(body.get("versions") or []) >= 1
        and isinstance(body.get("current"), str),
        "GET /api/map/transit/versions 返回历史列表",
    )

    status, body = http_request("POST", base_url + "/api/map/transit", payload={"data": {}})
    check(
        status == 401 and isinstance(body, dict) and body.get("code") == "unauthorized",
        "未登录 POST /api/map/transit 返回 401",
    )

    status, body = http_request("POST", base_url + "/api/map/transit/validate", payload={"data": {}})
    check(
        status == 401 and isinstance(body, dict) and body.get("code") == "unauthorized",
        "未登录 POST /api/map/transit/validate 返回 401",
    )

    status, body = http_request("POST", base_url + "/")
    check(
        status == 405 and isinstance(body, dict) and body.get("code") == "method_not_allowed",
        "错误请求方法返回 405 + code=method_not_allowed",
    )


def check_ws(ws_port: int) -> None:
    section("MCDR WS 命令服务")
    from websockets.sync.client import connect

    uri = f"ws://127.0.0.1:{ws_port}"
    try:
        with connect(uri, open_timeout=10) as ws:
            ws.send(json.dumps({"request_id": "ci-ping", "command": "ping"}))
            payload = json.loads(ws.recv(timeout=10))
    except Exception as exc:  # noqa: BLE001 - 连接/收发失败都视为 CI 失败
        fail(f"连接 WS 服务失败（{uri}）：{type(exc).__name__}: {exc}")
        return
    check(
        payload.get("request_id") == "ci-ping"
        and payload.get("success") is True
        and payload.get("data") == "pong",
        "WS ping → success=true / data=pong",
    )

    try:
        with connect(uri, open_timeout=10) as ws:
            ws.send(json.dumps({"request_id": "ci-unknown", "command": "ci_no_such_command"}))
            payload = json.loads(ws.recv(timeout=10))
    except Exception as exc:  # noqa: BLE001
        fail(f"WS 未知指令检查失败：{type(exc).__name__}: {exc}")
        return
    check(
        payload.get("request_id") == "ci-unknown" and payload.get("success") is False,
        "WS 未知指令 → success=false",
    )


def check_logs(log_text: str) -> None:
    section("启动 / 关闭日志")
    check("Traceback" not in log_text, "服务日志中没有 Traceback（无未捕获异常）")
    check("[ws-server] 监听" in log_text, "日志包含 MCDR WS 服务监听记录")
    check("Application startup complete" in log_text, "日志包含 uvicorn 启动完成记录")
    if os.name == "posix":
        # Windows 上 terminate() 是强制结束（无 SIGTERM 优雅关闭），仅在 POSIX（CI）断言。
        check("Application shutdown complete" in log_text, "日志包含 uvicorn 优雅关闭记录")
    else:
        print("[INFO] Windows 本地运行：terminate() 为强制结束，跳过「优雅关闭」断言")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    print("后端 CI 冒烟检查开始……", flush=True)
    check_syntax()
    probe_sqlite()

    original_config = None
    original_whs_config = None
    proc = None
    log_dir = None
    stdout_file = None
    stderr_file = None
    log_text = ""
    try:
        original_config, original_whs_config, http_port, ws_port = prepare_config()
        proc, log_dir, stdout_file, stderr_file = start_server(http_port)
        wait_ready(proc, http_port, log_dir)
        check_http(f"http://127.0.0.1:{http_port}")
        check_ws(ws_port)
    finally:
        if proc is not None:
            stop_server(proc)
        if stdout_file is not None:
            stdout_file.close()
        if stderr_file is not None:
            stderr_file.close()
        if log_dir is not None:
            log_text = read_logs(log_dir)
            shutil.rmtree(log_dir, ignore_errors=True)
        restore_config(original_config, original_whs_config)

    check_logs(log_text)
    print(f"\n全部通过：{_passed} 项检查 PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
