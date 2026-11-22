#!/usr/bin/env python3
"""MCDR 插件 CI 检查（mcdr_connecter_plugin/，插件 id：mcdr2web）。

由 .github/workflows/ci.yml 的「MCDR」job 调用；也可本地直接运行：

    python .github/scripts/mcdr_check.py
    python .github/scripts/mcdr_check.py --packed <pack 输出目录或 .mcdr>

检查内容：
1. mcdreforged.plugin.json 必填字段 / 版本格式 / 依赖声明；
2. 源码中 PLUGIN_METADATA 与清单逐字段一致（防止两处元数据漂移）；
3. 插件源码语法编译；
4. 用最小桩模块替代未入库的 whitelist_api / online_player_api 后真实导入插件，
   检查 MCDR 入口函数与 WS 命令表（含工程指令）；
5. 纯函数行为：`tick query` 解析（TPS/MSPT/health）、`list` 输出解析（玩家上限）；
6. 工程桥接：signup 缺失时返回 project_unavailable；用 signup 桩验证 create / claim /
   complete / update / delete 与错误码透传；
7. 可选 `--packed`：校验 mcdreforged pack 产出的 .mcdr 包内容与清单。

说明：CI 中 mcdreforged 与 websockets 由 workflow 安装；本地可借
      mcdr_connecter_plugin/venv 的 site-packages（设置 PYTHONPATH）运行。
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import importlib
import json
import re
import shutil
import sys
import tempfile
import types
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO_ROOT / "mcdr_connecter_plugin"
MANIFEST_PATH = PLUGIN_DIR / "mcdreforged.plugin.json"
SOURCE_PATH = PLUGIN_DIR / "mcdr2web" / "__init__.py"
PLUGIN_ID = "mcdr2web"

_passed = 0


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
# 1. 插件清单
# ---------------------------------------------------------------------------
def load_manifest() -> dict:
    section("插件清单（mcdreforged.plugin.json）")
    check(MANIFEST_PATH.is_file(), f"清单文件存在：{MANIFEST_PATH.relative_to(REPO_ROOT)}")
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"清单不是合法 JSON：{exc}")
    check(isinstance(manifest, dict), "清单顶层为 JSON 对象")

    for key in ("id", "version", "name", "description", "dependencies"):
        check(key in manifest, f"清单包含必填字段 {key}")
    check(manifest.get("id") == PLUGIN_ID, f"插件 id 为 {PLUGIN_ID}")
    version = str(manifest.get("version", ""))
    check(
        re.fullmatch(r"\d+\.\d+\.\d+", version) is not None,
        f"version 为 x.y.z 形式（当前 {version!r}）",
    )
    description = manifest.get("description")
    check(
        isinstance(description, dict)
        and bool(str(description.get("zh_cn") or "").strip())
        and bool(str(description.get("en_us") or "").strip()),
        "description 同时提供 zh_cn / en_us 文案",
    )
    dependencies = manifest.get("dependencies")
    check(isinstance(dependencies, dict), "dependencies 为对象")
    for dependency in ("mcdreforged", "whitelist_api", "online_player_api"):
        check(dependency in dependencies, f"声明依赖 {dependency}")
    mcdr_requirement = str(dependencies.get("mcdreforged") or "").replace(" ", "")
    check(mcdr_requirement.startswith(">="), "mcdreforged 依赖使用 >= 版本约束（与 README 一致）")
    return manifest


# ---------------------------------------------------------------------------
# 2. 源码元数据一致性 + 3. 语法
# ---------------------------------------------------------------------------
def check_source(manifest: dict) -> None:
    section("源码与清单一致性 / 语法")
    check(SOURCE_PATH.is_file(), f"插件入口存在：{SOURCE_PATH.relative_to(REPO_ROOT)}")

    source = SOURCE_PATH.read_text(encoding="utf-8")
    try:
        compile(source, str(SOURCE_PATH), "exec")
    except SyntaxError as exc:
        fail(f"插件源码语法错误：{exc}")
    ok("插件源码语法正确")

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        fail(f"插件源码无法解析为 AST：{exc}")
        return

    runtime_meta = None
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "PLUGIN_METADATA" for target in node.targets):
            try:
                runtime_meta = ast.literal_eval(node.value)
            except ValueError:
                runtime_meta = None
            break
    check(isinstance(runtime_meta, dict), "源码中存在 PLUGIN_METADATA 字典字面量")
    if not isinstance(runtime_meta, dict):
        return
    for key in ("id", "version", "name", "description", "dependencies"):
        check(
            runtime_meta.get(key) == manifest.get(key),
            f"源码 PLUGIN_METADATA.{key} 与 mcdreforged.plugin.json 一致",
        )


# ---------------------------------------------------------------------------
# 4. 桩导入 + 5. 纯函数行为
# ---------------------------------------------------------------------------
STUB_WHITELIST_API = '''"""CI 桩模块：替代未入库的 whitelist_api 插件（仅用于导入检查）。"""


def get_whitelist_names():
    return ["CI_Stub"]


def add_player(player):
    return True


def remove_player(player):
    return True
'''

STUB_ONLINE_PLAYER_API = '''"""CI 桩模块：替代未入库的 online_player_api 插件（仅用于导入检查）。"""


def get_player_list():
    return ["CI_Stub"]


def is_online(player, strict=True):
    return player == "CI_Stub"
'''


def import_plugin():
    section("桩导入 mcdr2web")
    stub_dir = Path(tempfile.mkdtemp(prefix="whs-ci-mcdr-stubs-"))
    (stub_dir / "whitelist_api").mkdir()
    (stub_dir / "whitelist_api" / "__init__.py").write_text(STUB_WHITELIST_API, encoding="utf-8")
    (stub_dir / "online_player_api").mkdir()
    (stub_dir / "online_player_api" / "__init__.py").write_text(
        STUB_ONLINE_PLAYER_API, encoding="utf-8"
    )

    # 目录顺序：桩目录优先于插件目录，保证本地存在真实依赖插件时也用桩。
    sys.path.insert(0, str(PLUGIN_DIR))
    sys.path.insert(0, str(stub_dir))
    try:
        plugin = importlib.import_module(PLUGIN_ID)
    except Exception as exc:  # noqa: BLE001 - 导入失败要打印完整上下文
        fail(f"导入 {PLUGIN_ID} 失败：{type(exc).__name__}: {exc}")
        return None
    finally:
        # 模块级导入已完成，桩目录可以删除（避免在临时目录留下垃圾）。
        shutil.rmtree(stub_dir, ignore_errors=True)
    ok(f"成功导入 {PLUGIN_ID}（mcdreforged + 桩依赖可用）")

    check(getattr(plugin, "PLUGIN_METADATA", {}).get("id") == PLUGIN_ID, "模块内 PLUGIN_METADATA.id 正确")
    for attribute in ("on_load", "on_unload", "parse_tick_query_output", "parse_list_output"):
        check(callable(getattr(plugin, attribute, None)), f"插件提供 {attribute}()")

    handlers = getattr(plugin, "command_handlers", None)
    expected_commands = {
        "ping",
        "get_player_list",
        "is_online",
        "get_whitelist",
        "add_player",
        "remove_player",
        "project_list",
        "project_get",
        "project_create",
        "project_claim",
        "project_complete",
        "project_delete",
        "project_update",
    }
    check(isinstance(handlers, dict), "插件注册了 WS 命令表 command_handlers")
    if isinstance(handlers, dict):
        check(expected_commands <= set(handlers), "WS 命令表包含后端约定的全部指令")
    return plugin


TICK_QUERY_OK = """\
[Server] [19:07:59] [Server thread/INFO]: The game is running normally
[Server] [19:07:59] [Server thread/INFO]: Target tick rate: 20.0 per second.
[Server] Average time per tick: 23.4ms (Target: 50.0ms)
[Server] [19:07:59] [Server thread/INFO]: Percentiles: P50: 22.9ms P95: 36.4ms P99: 41.9ms. Sample: 100
"""

TICK_QUERY_SLOW = """\
[Server] [19:07:59] [Server thread/INFO]: Target tick rate: 20.0 per second.
[Server] Average time per tick: 60.0ms (Target: 50.0ms)
"""


def check_parsers(plugin) -> None:
    section("纯函数行为")
    stats = plugin.parse_tick_query_output(TICK_QUERY_OK)
    check(isinstance(stats, dict), "解析正常 tick query 输出")
    if isinstance(stats, dict):
        check(stats.get("mspt") == 23.4, "MSPT 解析为 23.4")
        check(stats.get("tps") == 20.0, "MSPT <= 50ms 时 TPS 取目标 tick 率（20.0）")
        check(stats.get("healthy") is True, "健康状态解析为 True")

    slow = plugin.parse_tick_query_output(TICK_QUERY_SLOW)
    check(isinstance(slow, dict), "解析高 MSPT 的 tick query 输出")
    if isinstance(slow, dict):
        check(slow.get("tps") == 16.67, "MSPT 60ms 时 TPS = round(1000/60, 2) = 16.67")
        check(slow.get("healthy") is False, "无 running normally 时 healthy=False")

    check(plugin.parse_tick_query_output("") is None, "空文本解析返回 None")
    check(plugin.parse_tick_query_output("hello world") is None, "无 MSPT 的文本解析返回 None")

    check(
        plugin.parse_list_output("There are 3 of a max of 200 players online: Steve, Alex") == 200,
        "list 输出解析玩家上限 200",
    )
    check(plugin.parse_list_output("") is None, "空文本的玩家上限解析返回 None")
    check(plugin.parse_list_output("There are 0 players online") is None, "无 max 字段时返回 None")

    check(asyncio.run(plugin._handle_ping(None)) == "pong", "WS ping 处理器返回 pong")


# ---------------------------------------------------------------------------
# 6. 工程桥接（signup 桩）
# ---------------------------------------------------------------------------
STUB_SIGNUP = '''"""CI 桩模块：替代未入库的 signup 插件数据层（仅用于桥接检查）。"""


class SignUpError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


_PROJECTS = {}


def list_projects():
    return [dict(project, claimants=list(project.get("claimants") or [])) for project in _PROJECTS.values()]


def get_project(name):
    return _PROJECTS.get(name)


def create_project(name, creator):
    if name in _PROJECTS:
        raise SignUpError("project_exists")
    project = {"name": name, "creator": creator, "status": "unclaimed", "claimants": []}
    _PROJECTS[name] = project
    return project


def claim_project(name, player):
    project = _PROJECTS.get(name)
    if project is None:
        raise SignUpError("project_not_found")
    project["claimants"].append(player)
    project["status"] = "claimed"
    return project


def complete_project(name):
    project = _PROJECTS.get(name)
    if project is None:
        raise SignUpError("project_not_found")
    project["status"] = "completed"
    return project


def delete_project(name):
    if _PROJECTS.pop(name, None) is None:
        raise SignUpError("project_not_found")
    return {"success": True}


def update_project_meta(name, description=None, remark=None):
    project = _PROJECTS.get(name)
    if project is None:
        raise SignUpError("project_not_found")
    if description is not None:
        project["description"] = description
    if remark is not None:
        project["remark"] = remark
    return project
'''


def _install_signup_stub() -> None:
    module = types.ModuleType("signup")
    exec(compile(STUB_SIGNUP, "<signup-stub>", "exec"), module.__dict__)
    sys.modules["signup"] = module


def _expect_value_error(coro, code: str, message: str) -> None:
    try:
        asyncio.run(coro)
    except ValueError as exc:
        check(str(exc) == code, message)
    else:
        fail(f"{message}（未抛出 ValueError）")


def check_project_bridge(plugin) -> None:
    """检查 mcdr2web 的 project_* 指令：signup 缺失 / 桩成功路径 / 错误码透传。"""
    section("工程桥接（signup 桩）")
    sys.modules.pop("signup", None)
    _expect_value_error(
        plugin._handle_project_list(None),
        "project_unavailable",
        "signup 未加载时 project_list 返回 project_unavailable",
    )

    _install_signup_stub()
    try:
        created = asyncio.run(
            plugin._handle_project_create({"name": "ci project", "creator": "Steve"})
        )
        check(created["project"]["creator"] == "Steve", "project_create 透传创建者")

        listed = asyncio.run(plugin._handle_project_list(None))
        check(
            any(item.get("name") == "ci project" for item in listed.get("projects", [])),
            "project_list 返回新建工程",
        )

        claimed = asyncio.run(
            plugin._handle_project_claim({"name": "ci project", "player": "Alex"})
        )
        check(claimed["project"]["status"] == "claimed", "project_claim 更新为已认领")

        completed = asyncio.run(plugin._handle_project_complete({"name": "ci project"}))
        check(completed["project"]["status"] == "completed", "project_complete 更新为已完成")

        updated = asyncio.run(
            plugin._handle_project_update(
                {"name": "ci project", "description": "**md**", "remark": "note"}
            )
        )
        check(
            updated["project"]["description"] == "**md**"
            and updated["project"]["remark"] == "note",
            "project_update 写入描述与备注",
        )

        detail = asyncio.run(plugin._handle_project_get({"name": "ci project"}))
        check(detail["project"]["name"] == "ci project", "project_get 返回单个工程")

        deleted = asyncio.run(plugin._handle_project_delete({"name": "ci project"}))
        check(deleted.get("success") is True, "project_delete 返回 success")

        _expect_value_error(
            plugin._handle_project_get({"name": "missing"}),
            "project_not_found",
            "缺失工程返回 project_not_found",
        )
        _expect_value_error(
            plugin._handle_project_create({"name": "", "creator": "Steve"}),
            "project_name_invalid",
            "空工程名返回 project_name_invalid",
        )
    finally:
        sys.modules.pop("signup", None)


# ---------------------------------------------------------------------------
# 7. 打包产物
# ---------------------------------------------------------------------------
def check_packed(path: Path | None, manifest: dict) -> None:
    if path is None:
        print("\n[INFO] 未传入 --packed，跳过打包产物检查", flush=True)
        return
    section("打包产物（mcdreforged pack）")
    if path.is_dir():
        archives = sorted(path.glob("*.mcdr"))
        check(len(archives) == 1, f"打包目录中有且仅有 1 个 .mcdr 文件（实际 {len(archives)} 个）")
        archive = archives[0]
    else:
        archive = path
    check(archive.is_file(), f"打包产物存在：{archive}")

    with zipfile.ZipFile(archive) as zip_file:
        entries = {name.replace("\\", "/") for name in zip_file.namelist()}
        check("mcdreforged.plugin.json" in entries, "包内含 mcdreforged.plugin.json")
        check(f"{PLUGIN_ID}/__init__.py" in entries, f"包内含 {PLUGIN_ID}/__init__.py")
        check(
            not any(
                name.startswith(("whitelist_api/", "online_player_api/", "venv/", "__pycache__/"))
                for name in entries
            ),
            "包内不含未入库依赖 / venv / __pycache__",
        )
        packed_manifest = json.loads(zip_file.read("mcdreforged.plugin.json").decode("utf-8"))
        check(
            packed_manifest.get("id") == manifest.get("id")
            and packed_manifest.get("version") == manifest.get("version"),
            "包内清单 id/version 与仓库清单一致",
        )
        count = len(entries)
    ok(f"打包产物校验通过：{archive.name}（{count} 个条目，{archive.stat().st_size} 字节）")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MCDR 插件 CI 检查")
    parser.add_argument(
        "--packed",
        type=Path,
        default=None,
        help="mcdreforged pack 的输出目录（或单个 .mcdr 文件），用于额外校验打包产物",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    print("MCDR 插件 CI 检查开始……", flush=True)

    try:
        from importlib.metadata import version

        print(
            f"[INFO] mcdreforged {version('mcdreforged')} / "
            f"websockets {version('websockets')} / Python {sys.version.split()[0]}",
            flush=True,
        )
    except Exception:  # noqa: BLE001 - 版本信息仅用于日志
        print(f"[INFO] Python {sys.version.split()[0]}", flush=True)

    manifest = load_manifest()
    check_source(manifest)
    plugin = import_plugin()
    if plugin is None:
        return 1
    check_parsers(plugin)
    check_project_bridge(plugin)
    check_packed(args.packed, manifest)
    print(f"\n全部通过：{_passed} 项检查 PASS", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
