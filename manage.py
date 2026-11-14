#!/usr/bin/env python3
"""WHS Webpage 前后端统一启动管理器。

启动后同时托管两个子进程：
- 后端：backend/venv 的解释器运行 uvicorn（127.0.0.1:7777，dev 模式带 --reload）；
- 前端：whs/ 目录下运行 Vite
    dev  模式 -> npm run dev（开发服务器，5173）
    prod 模式 -> 先 npm run build，再 npm run preview（dist 产物 + /api 代理，5173）

两者的 stdout/stderr 会实时转发到终端（[HH:MM:SS.mmm] [来源] 行），
同时写入 logs/<启动时间>.log（[YYYY-MM-DD HH:MM:SS.mmm] [来源] 行）。

终止方式：
- 终端输入 stop / quit / exit 回车；
- Ctrl+C（Ctrl+Break 亦可）；
脚本会先终止前端，再终止后端，最后退出。

用法：
    python manage.py            # 交互选择前端环境
    python manage.py --dev      # 开发环境
    python manage.py --prod     # 生产环境
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# 项目路径与端口约定（后端 7777 见 vite.config.js 的代理配置，前端 5173 见 whs/package.json）
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "whs"
LOG_DIR = ROOT_DIR / "logs"

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 7777
FRONTEND_PORT = 5173
BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
FRONTEND_URL = f"http://localhost:{FRONTEND_PORT}"

IS_WINDOWS = os.name == "nt"
VENV_PYTHON = (
    BACKEND_DIR / "venv" / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")
)

# 关停时等待子进程自行退出的时间（秒），超时则强杀整个进程树。
GRACEFUL_TIMEOUT = 5.0
# 终端停止指令（不区分大小写）。
STOP_COMMANDS = {"stop", "quit", "exit"}


# ---------------------------------------------------------------------------
# 日志输出：终端 + 单一合并日志文件（每次启动新建一个）
# ---------------------------------------------------------------------------
class Logger:
    """线程安全的日志输出器：终端与日志文件使用各自要求的时间戳格式。"""

    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self._lock = threading.Lock()
        self._file = None
        self._write_error_reported = False
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(log_path, "a", encoding="utf-8", buffering=1)
        except OSError as exc:
            # 日志文件不可写不应阻断启动，退化为仅终端输出。
            print(f"[manager] 无法创建日志文件 {log_path}: {exc}", flush=True)

    def emit(self, source: str, text: str) -> None:
        """输出一行日志（来源如 manager / backend / frontend / frontend:build）。"""
        now = datetime.datetime.now()
        frac = now.microsecond // 1000
        terminal_line = f"[{now:%H:%M:%S}.{frac:03d}] [{source}] {text}"
        file_line = f"[{now:%Y-%m-%d %H:%M:%S}.{frac:03d}] [{source}] {text}"
        with self._lock:
            try:
                print(terminal_line, flush=True)
            except (OSError, ValueError):
                pass
            if self._file is not None:
                try:
                    self._file.write(file_line + "\n")
                except (OSError, ValueError) as exc:
                    if not self._write_error_reported:
                        self._write_error_reported = True
                        try:
                            print(f"[manager] 日志文件写入失败: {exc}", flush=True)
                        except (OSError, ValueError):
                            pass

    def close(self) -> None:
        with self._lock:
            if self._file is not None:
                try:
                    self._file.flush()
                    self._file.close()
                except (OSError, ValueError):
                    pass
                self._file = None


# ---------------------------------------------------------------------------
# 子进程托管：启动、逐行转发输出、优雅终止 / 强杀进程树
# ---------------------------------------------------------------------------
class ManagedProcess:
    """一个被托管的长期运行子进程（后端 / 前端）。"""

    def __init__(
        self,
        name: str,
        command: list[str],
        cwd: Path,
        logger: Logger,
        env: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.command = command
        self.cwd = cwd
        self.logger = logger
        self.env = env
        self.proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None

    # -- 启动 ---------------------------------------------------------------
    def start(self) -> None:
        kwargs: dict = {
            "cwd": str(self.cwd),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "env": self.env,
        }
        if IS_WINDOWS:
            # 独立进程组：终止时可对整个进程树发送 CTRL_BREAK。
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            # 独立会话：终止时可按进程组强杀。
            kwargs["start_new_session"] = True

        self.proc = subprocess.Popen(self.command, **kwargs)
        self._reader = threading.Thread(
            target=self._read_output,
            name=f"{self.name}-reader",
            daemon=True,
        )
        self._reader.start()

    def _read_output(self) -> None:
        """逐行读取子进程合并后的输出，转发到 Logger。"""
        stream = self.proc.stdout if self.proc else None
        if stream is None:
            return
        try:
            while True:
                raw = stream.readline()
                if not raw:
                    break
                text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                self.logger.emit(self.name, text)
        except (OSError, ValueError):
            pass
        finally:
            try:
                stream.close()
            except (OSError, ValueError):
                pass

    def _join_reader(self, timeout: float = 3.0) -> None:
        if self._reader is not None and self._reader.is_alive():
            self._reader.join(timeout=timeout)

    # -- 终止 ---------------------------------------------------------------
    def stop(self) -> None:
        """先请求优雅退出，超时则强杀进程树。"""
        proc = self.proc
        if proc is None:
            return
        if proc.poll() is not None:
            self.logger.emit(
                "manager", f"{self.name} 已退出（退出码 {proc.returncode}）"
            )
            self._join_reader()
            return

        self.logger.emit("manager", f"正在终止 {self.name}（pid={proc.pid}）…")
        try:
            if IS_WINDOWS:
                # 独立进程组 -> CTRL_BREAK 会发给该组内全部进程。
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.send_signal(signal.SIGTERM)
        except (OSError, ValueError) as exc:
            self.logger.emit(
                "manager",
                f"向 {self.name} 发送退出信号失败：{type(exc).__name__}: {exc}",
            )

        try:
            proc.wait(timeout=GRACEFUL_TIMEOUT)
            self.logger.emit(
                "manager", f"{self.name} 已退出（退出码 {proc.returncode}）"
            )
        except subprocess.TimeoutExpired:
            self.logger.emit(
                "manager",
                f"{self.name} 在 {GRACEFUL_TIMEOUT:.0f}s 内未退出，强制结束进程树",
            )
            _kill_process_tree(proc.pid)
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self.logger.emit("manager", f"{self.name} 强杀后仍未确认退出")
            else:
                self.logger.emit(
                    "manager", f"{self.name} 已强制退出（退出码 {proc.returncode}）"
                )
        finally:
            self._join_reader(timeout=3.0)


def _kill_process_tree(pid: int) -> None:
    """强制结束进程树：Windows 用 taskkill /T /F，POSIX 用进程组 SIGKILL。"""
    if IS_WINDOWS:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            os.kill(pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass


# ---------------------------------------------------------------------------
# 命令构造
# ---------------------------------------------------------------------------
def find_npm() -> list[str] | None:
    """返回可直接 Popen 的 npm 命令前缀；找不到返回 None。

    优先用 node + npm-cli.js（进程树最简单，不经过 cmd.exe），
    否则回退到 cmd.exe /c <npm.cmd>。
    """
    npm = shutil.which("npm")
    if npm is None:
        return None
    npm_path = Path(npm)
    node = shutil.which("node")
    if node and npm_path.suffix.lower() in (".cmd", ".bat"):
        npm_cli = npm_path.parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
        if npm_cli.is_file():
            return [node, str(npm_cli)]
    if IS_WINDOWS:
        return ["cmd.exe", "/c", f'"{npm_path}"']
    return [str(npm_path)]


def backend_command(dev: bool) -> list[str]:
    command = [
        str(VENV_PYTHON),
        "-u",
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        BACKEND_HOST,
        "--port",
        str(BACKEND_PORT),
    ]
    if dev:
        command.append("--reload")
    return command


def frontend_command(mode: str, npm: list[str]) -> list[str]:
    script = "dev" if mode == "dev" else "preview"
    return [*npm, "run", script]


def backend_env() -> dict[str, str]:
    env = os.environ.copy()
    # 子进程经管道输出：强制 UTF-8 + 不缓冲，避免中文乱码与日志滞后。
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONUTF8"] = "1"
    return env


# ---------------------------------------------------------------------------
# 启动前检查 / 生产构建
# ---------------------------------------------------------------------------
def preflight() -> list[str]:
    """返回启动前发现的错误列表（空列表表示通过）。"""
    errors: list[str] = []
    if not BACKEND_DIR.is_dir():
        errors.append(f"未找到后端目录：{BACKEND_DIR}")
    if not VENV_PYTHON.is_file():
        errors.append(
            f"未找到后端虚拟环境解释器：{VENV_PYTHON}"
            "（请先在 backend/ 创建 venv 并安装 requirements.txt）"
        )
    if not (FRONTEND_DIR / "package.json").is_file():
        errors.append(f"未找到前端 package.json：{FRONTEND_DIR / 'package.json'}")
    if not (FRONTEND_DIR / "node_modules").is_dir():
        errors.append(
            f"未找到前端依赖目录：{FRONTEND_DIR / 'node_modules'}"
            "（请先在 whs/ 执行 npm install）"
        )
    if find_npm() is None:
        errors.append("未在 PATH 中找到 npm，请确认 Node.js 已安装并可用")
    return errors


def run_build(logger: Logger, npm: list[str]) -> int:
    """生产模式：同步执行一次前端构建并转发输出，返回构建退出码。"""
    logger.emit("manager", "生产模式：开始构建前端（npm run build）…")
    build = ManagedProcess(
        "frontend:build",
        [*npm, "run", "build"],
        FRONTEND_DIR,
        logger,
    )
    build.start()
    try:
        return_code = build.proc.wait()
    except KeyboardInterrupt:
        logger.emit("manager", "前端构建被中断，正在终止构建进程…")
        build.stop()
        raise
    finally:
        build._join_reader(timeout=5.0)  # noqa: SLF001 - 同一模块内部使用

    if return_code == 0:
        logger.emit("manager", "前端构建完成。")
    else:
        logger.emit("manager", f"前端构建失败（退出码 {return_code}），取消启动。")
    return return_code


# ---------------------------------------------------------------------------
# 模式选择 / 终端指令 / 信号处理
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="WHS Webpage 前后端统一启动管理器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python manage.py            # 交互选择\n"
            "  python manage.py --dev      # 开发环境\n"
            "  python manage.py --prod     # 生产环境（先 build 再 preview）\n"
            "运行中输入 stop / quit / exit 回车，或按 Ctrl+C 停止。"
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dev", action="store_true", help="前端开发环境（npm run dev）")
    group.add_argument(
        "--prod", action="store_true", help="前端生产环境（npm run build + npm run preview）"
    )
    return parser.parse_args()


def resolve_mode(args: argparse.Namespace) -> str | None:
    """确定前端模式：命令行参数优先，缺省时交互询问；取消返回 None。"""
    if args.dev:
        return "dev"
    if args.prod:
        return "prod"

    print("请选择前端运行环境：")
    print("  [1] 开发环境 dev  —— npm run dev（带热更新，后端 --reload）")
    print("  [2] 生产环境 prod —— npm run build + npm run preview（后端不带 --reload）")
    while True:
        try:
            answer = input("请输入 1 或 2（直接回车 = 1，Ctrl+C 取消）：").strip()
        except EOFError:
            print("\n终端输入已关闭，默认使用开发环境 dev。")
            return "dev"
        if answer == "":
            return "dev"
        if answer in {"1", "dev", "d"}:
            return "dev"
        if answer in {"2", "prod", "p"}:
            return "prod"
        print("输入无效，请重新输入 1 或 2。")


def start_stdin_listener(stop_event: threading.Event, state: dict, logger: Logger) -> None:
    """后台线程：监听终端输入的 stop / quit / exit 指令。"""
    while not stop_event.is_set():
        try:
            line = input()
        except EOFError:
            logger.emit("manager", "终端输入已关闭，stop 指令不可用（仍可按 Ctrl+C 停止）。")
            return
        except (OSError, ValueError):
            return
        command = line.strip().lower()
        if command in STOP_COMMANDS:
            state["reason"] = f"收到终端指令 {command}"
            logger.emit("manager", f"收到终端指令 {command}，准备停止…")
            stop_event.set()
            return
        if command:
            logger.emit("manager", f"未知指令 {command!r}（可用：stop / quit / exit）")


def install_signal_handlers(stop_event: threading.Event, state: dict, logger: Logger) -> None:
    """SIGTERM / SIGBREAK 转为统一停止请求；SIGINT 保留默认行为（KeyboardInterrupt）。"""
    def handler(signum, _frame) -> None:
        state["reason"] = f"收到信号 {signum}"
        logger.emit("manager", f"收到信号 {signum}，准备停止…")
        stop_event.set()

    for name in ("SIGTERM", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, handler)
        except (OSError, ValueError):
            pass


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def _emit_banner(logger: Logger, dev: bool, npm: list[str], log_path: Path) -> None:
    mode_text = "开发 dev" if dev else "生产 prod"
    logger.emit("manager", "=" * 66)
    logger.emit("manager", "WHS Webpage 启动管理器")
    logger.emit("manager", f"模式：{mode_text}")
    logger.emit("manager", f"后端命令：{' '.join(backend_command(dev))}（cwd={BACKEND_DIR}）")
    frontend_plan = "npm run build + npm run preview" if not dev else "npm run dev"
    logger.emit("manager", f"前端命令：{frontend_plan}（cwd={FRONTEND_DIR}）")
    logger.emit("manager", f"日志文件：{log_path}")
    logger.emit("manager", "=" * 66)


def _emit_ready(logger: Logger, dev: bool, backend: ManagedProcess, frontend: ManagedProcess, log_path: Path) -> None:
    logger.emit("manager", "-" * 66)
    logger.emit("manager", f"后端已启动：{BACKEND_URL}（pid={backend.proc.pid}）")
    logger.emit(
        "manager",
        f"前端已启动：{FRONTEND_URL}（pid={frontend.proc.pid}）"
        + ("" if dev else "，服务的是 whs/dist 构建产物"),
    )
    logger.emit("manager", f"前端若因端口占用自动换端口，请以日志中的 Local URL 为准。")
    logger.emit("manager", f"日志：{log_path}")
    logger.emit("manager", "输入 stop / quit / exit 回车，或按 Ctrl+C 停止（先停前端，再停后端）。")
    logger.emit("manager", "-" * 66)


def _monitor(
    stop_event: threading.Event,
    state: dict,
    processes: list[ManagedProcess],
    logger: Logger,
) -> str:
    """等待停止请求；若某个子进程意外退出则触发整体停止。"""
    while not stop_event.is_set():
        for process in processes:
            if process.proc is None:
                continue
            code = process.proc.poll()
            if code is not None:
                logger.emit(
                    "manager",
                    f"{process.name} 意外退出（退出码 {code}），将停止其余服务。",
                )
                state["reason"] = f"{process.name} 意外退出（退出码 {code}）"
                return state["reason"]
        stop_event.wait(0.5)
    return state.get("reason", "收到停止请求")


def main() -> int:
    args = parse_args()
    try:
        mode = resolve_mode(args)
    except KeyboardInterrupt:
        print("\n已取消启动。")
        return 130
    if mode is None:
        print("已取消启动。")
        return 130
    dev = mode == "dev"

    started_at = datetime.datetime.now()
    log_path = LOG_DIR / f"{started_at:%Y%m%d-%H%M%S}.log"
    logger = Logger(log_path)
    npm = find_npm()

    backend: ManagedProcess | None = None
    frontend: ManagedProcess | None = None
    stop_event = threading.Event()
    state: dict[str, str] = {"reason": "收到停止请求"}
    exit_code = 0
    stop_reason = "启动未完成"

    try:
        _emit_banner(logger, dev, npm or [], log_path)

        errors = preflight()
        if errors:
            for message in errors:
                logger.emit("manager", f"[启动前检查失败] {message}")
            exit_code = 2
            return exit_code
        assert npm is not None  # preflight 已保证

        if not dev:
            if run_build(logger, npm) != 0:
                exit_code = 1
                return exit_code

        backend = ManagedProcess(
            "backend",
            backend_command(dev),
            BACKEND_DIR,
            logger,
            env=backend_env(),
        )
        backend.start()
        logger.emit("manager", f"后端进程已启动（pid={backend.proc.pid}）")

        frontend = ManagedProcess(
            "frontend",
            frontend_command(mode, npm),
            FRONTEND_DIR,
            logger,
        )
        frontend.start()
        logger.emit("manager", f"前端进程已启动（pid={frontend.proc.pid}）")

        _emit_ready(logger, dev, backend, frontend, log_path)

        install_signal_handlers(stop_event, state, logger)
        if sys.stdin is not None and sys.stdin.isatty():
            threading.Thread(
                target=start_stdin_listener,
                args=(stop_event, state, logger),
                name="stdin-listener",
                daemon=True,
            ).start()
        else:
            logger.emit(
                "manager",
                "当前终端不支持输入指令（stdin 非交互），请用 Ctrl+C 或信号停止。",
            )

        stop_reason = _monitor(stop_event, state, [backend, frontend], logger)
    except KeyboardInterrupt:
        stop_reason = "Ctrl+C"
        logger.emit("manager", "收到 Ctrl+C。")
    except Exception as exc:  # noqa: BLE001 - 顶层兜底，保证子进程被清理
        stop_reason = f"运行异常：{type(exc).__name__}: {exc}"
        logger.emit("manager", f"运行异常：{type(exc).__name__}: {exc}")
        exit_code = 1
    finally:
        if backend is not None or frontend is not None:
            logger.emit(
                "manager",
                f"开始关停（原因：{stop_reason}）：先终止前端，再终止后端…",
            )
            # 需求顺序：先前端、后后端。
            if frontend is not None:
                frontend.stop()
            if backend is not None:
                backend.stop()
            logger.emit("manager", "前端、后端均已停止。")
        else:
            logger.emit("manager", "未启动任何子进程，直接退出。")
        logger.close()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
