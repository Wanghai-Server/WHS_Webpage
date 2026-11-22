"""轨交路线图数据层：追加式多版本文档 + 校验 + 三方合并。

文件 ``data/transit.yml`` 是**运行时文件**（不入库），由后端启动时自动创建。
它由多个 YAML 文档组成：

    format: 1
    ---
    id: "a1b2c3"
    parent: null
    created_at: ...
    author: {uid: 1, name: seed}
    summary: 初始化
    data: {note: ..., lines: [...], stations: [...]}

提交只**在文件尾部追加**一个新文档，历史字节不动，写放大 = 单版本大小。
版本数超过 ``MAX_VERSIONS`` 或文件超过 ``MAX_BYTES`` 时才压实重写一次。

版本 ID = sha256(canonical({parent, data}))[:6]；同内容同父版本得到同一个 ID，
重复提交直接返回已有版本、不写盘（幂等）。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path

import yaml

TRANSIT_PATH = Path(__file__).resolve().parent / "transit.yml"
MAX_VERSIONS = 200
MAX_BYTES = 8 * 1024 * 1024

_LOCK = threading.RLock()

_ID_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

LINE_TYPES = ("metro", "rail", "bus")
LINE_STATUS = ("open", "building", "planned")
Y_SOURCES = ("explicit", "picked")

# 坐标范围与 Minecraft 世界边界一致
_POS_LIMIT = 30_000_000

LINE_FIELDS = ("name", "color", "type", "status", "note", "stations")
STATION_FIELDS = ("name", "pos", "y", "y_source", "tags", "note")


class TransitConfigError(ValueError):
    """轨交数据不合法（消息里带位置）。"""


class TransitConflictError(ValueError):
    """并发提交冲突：需要人工解决。"""

    def __init__(self, conflicts: list[dict], base_version: str, current_version: str):
        self.conflicts = conflicts
        self.base_version = base_version
        self.current_version = current_version
        super().__init__(f"conflicts with {current_version}: {len(conflicts)} 处")


# ---------------------------------------------------------------------------
# 持久化：多文档 YAML
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _read_docs(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    docs = []
    for raw in yaml.safe_load_all(text):
        if isinstance(raw, dict) and raw:
            docs.append(raw)
    return docs


def _split_docs(docs: list[dict]) -> tuple[dict, list[dict]]:
    """第一个文档是头部（format），其余是版本。"""
    if not docs or "format" not in docs[0]:
        raise TransitConfigError("transit.yml 缺少头部文档（format）")
    return docs[0], [doc for doc in docs[1:] if "id" in doc]


def read_store(path: Path | None = None) -> dict:
    target = Path(path) if path else TRANSIT_PATH
    with _LOCK:
        if not target.exists():
            ensure_transit_file(target)
        try:
            header, versions = _split_docs(_read_docs(target))
        except TransitConfigError:
            raise
        except Exception as exc:
            raise TransitConfigError(f"{target.name} 解析失败：{exc}") from None
        return {"format": int(header.get("format") or 1), "versions": versions}


def current_version(store: dict) -> dict | None:
    versions = store.get("versions") or []
    return versions[-1] if versions else None


def load_current(path: Path | None = None) -> tuple[dict, str, list[str]]:
    """返回 (规范化后的 data, version_id, warnings)。"""
    store = read_store(path)
    version = current_version(store)
    if version is None:
        raise TransitConfigError("transit.yml 里没有任何版本")
    data, warnings = validate_data(version.get("data"))
    return data, str(version.get("id")), warnings


# ---------------------------------------------------------------------------
# 校验与规范化
# ---------------------------------------------------------------------------
def _fail(where: str, message: str) -> None:
    raise TransitConfigError(f"{where}: {message}")


def _text(where: str, value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(where, f"{field} 必须是非空字符串")
    return value.strip()


def _i18n(where: str, value, field: str = "name") -> dict[str, str]:
    if not isinstance(value, dict):
        _fail(where, f"{field} 必须是 {{zh, en}} 对象")
    out: dict[str, str] = {}
    for lang in ("zh", "en"):
        text = value.get(lang)
        if isinstance(text, str) and text.strip():
            out[lang] = text.strip()
    if not out:
        _fail(where, f"{field} 至少要有一个语言")
    return out


def _point(where: str, value) -> list[int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        _fail(where, "pos 必须是 [x, z] 两个整数")
    out: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            _fail(where, "pos 必须是整数")
        if abs(item) > _POS_LIMIT:
            _fail(where, f"pos 超出范围 ±{_POS_LIMIT}")
        out.append(item)
    return out


def validate_data(raw, *, require_lines: bool = False) -> tuple[dict, list[str]]:
    """校验并规范化一个版本的 ``data``，返回 (data, warnings)。"""
    if not isinstance(raw, dict):
        _fail("data", "顶层必须是对象")

    lines_raw = raw.get("lines")
    stations_raw = raw.get("stations")
    if not isinstance(lines_raw, list):
        _fail("data", "lines 必须是数组")
    if not isinstance(stations_raw, list):
        _fail("data", "stations 必须是数组")

    stations: dict[str, dict] = {}
    for index, item in enumerate(stations_raw):
        where = f"stations[{index}]"
        if not isinstance(item, dict):
            _fail(where, "车站必须是对象")
        sid = _text(where, item.get("id"), "id")
        if not _ID_RE.match(sid):
            _fail(where, "id 只能用小写字母、数字、下划线、连字符，最长 32")
        if sid in stations:
            _fail(where, f"车站 id 重复：{sid}")

        entry: dict = {
            "id": sid,
            "name": _i18n(where, item.get("name")),
            "pos": _point(where, item.get("pos")),
        }
        if item.get("y") is not None:
            y = item["y"]
            if isinstance(y, bool) or not isinstance(y, (int, float)):
                _fail(where, "y 必须是数字")
            entry["y"] = y
            source = item.get("y_source") or "explicit"
            if source not in Y_SOURCES:
                _fail(where, f"y_source 只能是 {'/'.join(Y_SOURCES)}")
            entry["y_source"] = source
        if item.get("tags") is not None:
            tags = item["tags"]
            if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
                _fail(where, "tags 必须是字符串数组")
            entry["tags"] = [t.strip() for t in tags if t.strip()]
        if item.get("note") is not None:
            entry["note"] = _i18n(where, item["note"], "note")
        stations[sid] = entry

    lines: list[dict] = []
    used: dict[str, list[str]] = {}
    colors: dict[str, str] = {}
    warnings: list[str] = []

    for index, item in enumerate(lines_raw):
        where = f"lines[{index}]"
        if not isinstance(item, dict):
            _fail(where, "线路必须是对象")
        lid = _text(where, item.get("id"), "id")
        if not _ID_RE.match(lid):
            _fail(where, "id 只能用小写字母、数字、下划线、连字符，最长 32")
        if any(line["id"] == lid for line in lines):
            _fail(where, f"线路 id 重复：{lid}")

        color = _text(where, item.get("color"), "color")
        if not _COLOR_RE.match(color):
            _fail(where, "color 必须是 #RRGGBB")
        color = color.lower()
        if color in colors:
            warnings.append(f"线路 {lid} 与 {colors[color]} 用了同一个颜色 {color}")
        colors[color] = lid

        ltype = item.get("type") or "metro"
        if ltype not in LINE_TYPES:
            _fail(where, f"type 只能是 {'/'.join(LINE_TYPES)}")
        status = item.get("status") or "open"
        if status not in LINE_STATUS:
            _fail(where, f"status 只能是 {'/'.join(LINE_STATUS)}")

        sequence = item.get("stations")
        if not isinstance(sequence, list) or len(sequence) < 2:
            _fail(where, "stations 必须是至少 2 个站 id 的数组")
        clean: list[str] = []
        for pos, sid in enumerate(sequence):
            if not isinstance(sid, str):
                _fail(f"{where}.stations[{pos}]", "站 id 必须是字符串")
            if sid not in stations:
                _fail(f"{where}.stations[{pos}]", f"引用了不存在的车站 {sid}")
            if clean and clean[-1] == sid:
                _fail(f"{where}.stations[{pos}]", f"相邻重复站 {sid}")
            if sid in clean:
                _fail(f"{where}.stations[{pos}]", f"同一线路里重复出现 {sid}")
            clean.append(sid)
            used.setdefault(sid, []).append(lid)

        line = {
            "id": lid,
            "name": _i18n(where, item.get("name")),
            "color": color,
            "type": ltype,
            "status": status,
            "stations": clean,
        }
        if item.get("note") is not None:
            line["note"] = _i18n(where, item["note"], "note")
        lines.append(line)

    for sid, entry in stations.items():
        entry["lines"] = used.get(sid, [])
        if not entry["lines"]:
            warnings.append(f"车站 {sid} 没有被任何线路引用")

    if require_lines and not lines:
        _fail("data", "lines 不能为空")

    normalized: dict = {"lines": lines, "stations": list(stations.values())}
    if raw.get("note") is not None:
        normalized["note"] = _i18n("data", raw["note"], "note")
    return normalized, warnings


# ---------------------------------------------------------------------------
# 版本 ID
# ---------------------------------------------------------------------------
def _base_version_id(parent: str | None, data: dict) -> str:
    payload = _canonical({"parent": parent, "data": data})
    return hashlib.sha256(payload).hexdigest()


def version_id(parent: str | None, data: dict, existing: set[str] | None = None) -> str:
    """版本 ID：SHA256 前 6 位；与现有版本撞车时依次加长。"""
    digest = _base_version_id(parent, data)
    length = 6
    while existing and digest[:length] in existing and length < len(digest):
        length += 1
    return digest[:length]


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------
def _append_doc(doc: dict, path: Path) -> None:
    """追加一个版本；写后校验，失败则截断回原长度。"""
    with _LOCK:
        size_before = path.stat().st_size
        text = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, default_flow_style=False)
        try:
            with path.open("a", encoding="utf-8") as handle:
                if size_before and not _ends_with_newline(path, size_before):
                    handle.write("\n")
                handle.write("---\n")
                handle.write(text)
                handle.flush()
            _, versions = _split_docs(_read_docs(path))
            if not versions or versions[-1].get("id") != doc.get("id"):
                raise TransitConfigError("追加后校验失败")
        except Exception:
            try:
                with path.open("r+b") as handle:
                    handle.truncate(size_before)
            except OSError:
                pass
            raise


def _ends_with_newline(path: Path, size: int) -> bool:
    with path.open("rb") as handle:
        handle.seek(max(size - 1, 0))
        return handle.read(1) == b"\n"


def _write_header(handle) -> None:
    handle.write("# WHS 轨交路线图：追加式版本库，勿手改结构\n")
    handle.write(yaml.safe_dump({"format": 1}, allow_unicode=True, sort_keys=False))


def _write_all(versions: list[dict], path: Path) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        _write_header(handle)
        for doc in versions:
            handle.write("---\n")
            handle.write(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, default_flow_style=False))
    os.replace(tmp, path)


def seed_version() -> dict:
    """种子版本：一条示例线、两个车站（首次启动时写入）。"""
    data = {
        "note": {"zh": "示意图，非等比", "en": "Schematic, not to scale"},
        "lines": [
            {
                "id": "l1",
                "name": {"zh": "1号线", "en": "Line 1"},
                "color": "#2f7fe0",
                "type": "metro",
                "status": "open",
                "stations": ["s_origin", "s_hub", "s_harbour", "s_dock"],
            },
            {
                "id": "l2",
                "name": {"zh": "2号线", "en": "Line 2"},
                "color": "#e2554a",
                "type": "metro",
                "status": "open",
                "stations": ["s_mine", "s_hub", "s_market"],
            },
            {
                "id": "l3",
                "name": {"zh": "临港支线", "en": "Harbour Branch"},
                "color": "#f0a020",
                "type": "rail",
                "status": "building",
                "note": {"zh": "在建，2026 年内开通", "en": "Under construction"},
                "stations": ["s_harbour", "s_newland"],
            },
        ],
        "stations": [
            {
                "id": "s_origin",
                "name": {"zh": "起点站", "en": "Origin"},
                "pos": [0, 0],
                "note": {"zh": "示例数据，请在编辑器里替换为真实线路", "en": "Seed data, replace it in the editor"},
            },
            {"id": "s_hub", "name": {"zh": "中枢站", "en": "Hub"}, "pos": [240, 0], "tags": ["hub"], "note": {"zh": "1、2 号线换乘", "en": "Interchange of lines 1 and 2"}},
            {"id": "s_harbour", "name": {"zh": "港区站", "en": "Harbour"}, "pos": [480, 0], "tags": ["shop"]},
            {"id": "s_dock", "name": {"zh": "码头站", "en": "Dock"}, "pos": [480, -240]},
            {"id": "s_mine", "name": {"zh": "矿场站", "en": "Mine"}, "pos": [0, -240]},
            {"id": "s_market", "name": {"zh": "市场站", "en": "Market"}, "pos": [240, 240], "tags": ["shop"]},
            {"id": "s_newland", "name": {"zh": "新陆站", "en": "Newland"}, "pos": [480, 240]},
        ],
    }
    normalized, _ = validate_data(data)
    return {
        "id": version_id(None, normalized),
        "parent": None,
        "created_at": _now(),
        "author": {"uid": 0, "name": "seed"},
        "summary": "初始化",
        "data": normalized,
    }


def ensure_transit_file(path: Path | None = None) -> bool:
    """启动时检查：文件不存在或为空则用种子创建，返回是否新建。"""
    target = Path(path) if path else TRANSIT_PATH
    with _LOCK:
        if target.exists() and target.stat().st_size > 0:
            return False
        doc = seed_version()
        tmp = target.with_name(target.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            _write_header(handle)
            handle.write("---\n")
            handle.write(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, default_flow_style=False))
        os.replace(tmp, target)
        return True


# ---------------------------------------------------------------------------
# 三方合并
# ---------------------------------------------------------------------------
def _flatten(value, prefix: str = "") -> dict[str, object]:
    """把对象摊平成 {点路径: 标量/列表}；列表视作原子值。"""
    flat: dict[str, object] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            flat.update(_flatten(item, f"{prefix}.{key}" if prefix else str(key)))
    else:
        flat[prefix] = value
    return flat


def _unflatten(flat: dict[str, object]) -> dict:
    root: dict = {}
    for path, value in sorted(flat.items()):
        parts = path.split(".")
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return root


def _merge_object(base: dict | None, current: dict | None, incoming: dict | None,
                  where: str, conflicts: list[dict]) -> dict | None:
    """对象级三方合并（字段级冲突检测）。返回合并后的对象（可能为 None = 删除）。"""
    if _eq(base, current):
        return incoming
    if _eq(base, incoming):
        return current
    if _eq(current, incoming):
        return current
    if current is None or incoming is None:
        conflicts.append({
            "path": where,
            "base": base,
            "current": current,
            "incoming": incoming,
            "reason": "deleted",
        })
        return current
    if base is None:
        base = {}

    fb, fc, fi = _flatten(base or {}), _flatten(current), _flatten(incoming)
    merged: dict[str, object] = {}
    for path in sorted(set(fb) | set(fc) | set(fi)):
        bv, cv, iv = fb.get(path, _MISSING), fc.get(path, _MISSING), fi.get(path, _MISSING)
        if _eq(cv, iv):
            value = cv
        elif _eq(bv, cv):
            value = iv
        elif _eq(bv, iv):
            value = cv
        else:
            conflicts.append({
                "path": f"{where}.{path}",
                "base": None if bv is _MISSING else bv,
                "current": None if cv is _MISSING else cv,
                "incoming": None if iv is _MISSING else iv,
            })
            value = cv
        if value is not _MISSING:
            merged[path] = value
    return _unflatten(merged) or None


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return "<missing>"


_MISSING = _Missing()


def _eq(a, b) -> bool:
    # 哨兵值不参与序列化，只在「同为缺失」时相等
    if a is _MISSING or b is _MISSING:
        return a is b
    return _canonical(a) == _canonical(b)


def _merge_collection(base: list, current: list, incoming: list, kind: str,
                      conflicts: list[dict]) -> list:
    def index(items):
        return {item.get("id"): item for item in items if isinstance(item, dict) and item.get("id")}

    bc, cc, ic = index(base or []), index(current or []), index(incoming or [])
    result: list[dict] = []
    for key in sorted(set(bc) | set(cc) | set(ic)):
        merged = _merge_object(bc.get(key), cc.get(key), ic.get(key), f"{kind}[{key}]", conflicts)
        if merged is not None:
            result.append(merged)
    # 保持 incoming 的顺序，新增对象按 incoming 的顺序排在后面
    order = {item.get("id"): pos for pos, item in enumerate(incoming or []) if isinstance(item, dict)}
    result.sort(key=lambda item: (order.get(item.get("id"), 10 ** 6), str(item.get("id"))))
    return result


def merge_three_way(base: dict, current: dict, incoming: dict) -> tuple[dict, list[dict]]:
    """三方合并；返回 (合并结果, 冲突列表)。"""
    conflicts: list[dict] = []
    merged: dict = {}
    merged["lines"] = _merge_collection(base.get("lines"), current.get("lines"),
                                        incoming.get("lines"), "lines", conflicts)
    merged["stations"] = _merge_collection(base.get("stations"), current.get("stations"),
                                           incoming.get("stations"), "stations", conflicts)
    note = _merge_object(base.get("note"), current.get("note"), incoming.get("note"), "note", conflicts)
    if note:
        merged["note"] = note
    return merged, conflicts


def diff_versions(left: dict, right: dict) -> list[dict]:
    """结构化 diff：按对象 / 字段给出变化，供前端对比。"""
    changes: list[dict] = []
    for kind in ("lines", "stations"):
        a = {item["id"]: item for item in left.get(kind) or []}
        b = {item["id"]: item for item in right.get(kind) or []}
        for key in sorted(set(a) | set(b)):
            if key not in a:
                changes.append({"type": "added", "path": f"{kind}[{key}]", "value": b[key]})
            elif key not in b:
                changes.append({"type": "removed", "path": f"{kind}[{key}]", "value": a[key]})
            else:
                fa, fb = _flatten(a[key]), _flatten(b[key])
                for path in sorted(set(fa) | set(fb)):
                    if not _eq(fa.get(path), fb.get(path)):
                        changes.append({
                            "type": "changed",
                            "path": f"{kind}[{key}].{path}",
                            "old": fa.get(path),
                            "new": fb.get(path),
                        })
    fa, fb = _flatten(left.get("note") or {}), _flatten(right.get("note") or {})
    for path in sorted(set(fa) | set(fb)):
        if not _eq(fa.get(path), fb.get(path)):
            changes.append({"type": "changed", "path": f"note.{path}", "old": fa.get(path), "new": fb.get(path)})
    return changes


# ---------------------------------------------------------------------------
# 提交 / 回退 / 压实
# ---------------------------------------------------------------------------
def _stats(data: dict) -> dict:
    return {"lines": len(data.get("lines") or []), "stations": len(data.get("stations") or [])}


def _public_version(doc: dict, include_data: bool = False) -> dict:
    out = {
        "id": doc.get("id"),
        "parent": doc.get("parent"),
        "created_at": doc.get("created_at"),
        "author": doc.get("author") or {},
        "summary": doc.get("summary") or "",
        "stats": _stats(doc.get("data") or {}),
    }
    if include_data:
        out["data"] = doc.get("data")
    return out


def _maybe_compact(path: Path, store: dict) -> bool:
    versions = store.get("versions") or []
    if len(versions) <= MAX_VERSIONS and path.stat().st_size <= MAX_BYTES:
        return False
    keep = versions[-MAX_VERSIONS:]
    backup = path.with_name(path.name + ".bak")
    try:
        shutil.copyfile(path, backup)
    except OSError:
        pass
    _write_all(keep, path)
    return True


def submit(data, *, base_version: str | None, author: dict, summary: str,
           force: bool = False, path: Path | None = None) -> dict:
    """提交一个新版本。返回 {created, version, data, merged, conflicts}。"""
    target = Path(path) if path else TRANSIT_PATH
    normalized, warnings = validate_data(data, require_lines=True)

    with _LOCK:
        store = read_store(target)
        versions = store.get("versions") or []
        current = current_version(store)
        current_id = str(current.get("id")) if current else None
        existing = {str(doc.get("id")) for doc in versions}

        # 幂等：提交内容与当前版本完全一致时直接返回，不写盘
        if current is not None:
            current_data, _ = validate_data(current.get("data"))
            if _eq(normalized, current_data):
                return {
                    "created": False,
                    "version": current_id,
                    "data": current_data,
                    "warnings": warnings,
                    "summary": current.get("summary"),
                }

        merged_note = False
        if current is not None and base_version != current_id:
            base = next((doc for doc in versions if str(doc.get("id")) == base_version), None)
            if base is None:
                raise TransitConflictError([], str(base_version or ""), str(current_id))
            if not force:
                merged, conflicts = merge_three_way(base.get("data") or {}, current.get("data") or {}, normalized)
                if conflicts:
                    raise TransitConflictError(conflicts, str(base_version), str(current_id))
                normalized, warnings = validate_data(merged, require_lines=True)
                merged_note = True

        vid = version_id(current_id, normalized, existing)
        if vid in existing:
            doc = next(item for item in versions if str(item.get("id")) == vid)
            return {
                "created": False,
                "version": vid,
                "data": doc.get("data"),
                "warnings": warnings,
                "summary": doc.get("summary"),
            }

        final_summary = (summary or "").strip() or "更新路线图"
        if merged_note:
            final_summary += "（自动合并）"
        if force and current is not None and base_version != current_id:
            final_summary += "（强制并入）"

        doc = {
            "id": vid,
            "parent": current_id,
            "created_at": _now(),
            "author": author,
            "summary": final_summary,
            "data": normalized,
        }
        _append_doc(doc, target)
        compacted = _maybe_compact(target, read_store(target))
        return {
            "created": True,
            "version": vid,
            "data": normalized,
            "warnings": warnings,
            "summary": final_summary,
            "compacted": compacted,
        }


def rollback(target_id: str, *, author: dict, summary: str | None = None,
             path: Path | None = None) -> dict:
    target = Path(path) if path else TRANSIT_PATH
    store = read_store(target)
    doc = next((item for item in store.get("versions") or [] if str(item.get("id")) == target_id), None)
    if doc is None:
        raise TransitConfigError(f"版本 {target_id} 不存在")
    current = current_version(store)
    result = submit(
        doc.get("data") or {},
        base_version=str(current.get("id")) if current else None,
        author=author,
        summary=summary or f"回退到 {target_id}",
        path=target,
    )
    return result


def compact(path: Path | None = None, keep: int = MAX_VERSIONS) -> dict:
    target = Path(path) if path else TRANSIT_PATH
    with _LOCK:
        store = read_store(target)
        versions = store.get("versions") or []
        before = len(versions)
        if before <= keep:
            return {"compacted": False, "versions": before}
        backup = target.with_name(target.name + ".bak")
        try:
            shutil.copyfile(target, backup)
        except OSError:
            pass
        _write_all(versions[-keep:], target)
        return {"compacted": True, "before": before, "after": keep}
