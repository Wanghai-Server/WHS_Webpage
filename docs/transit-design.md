# 轨交路线图设计

## 范围

- 公开只读页 `/map/transit`：SVG 示意图、图例过滤、站名搜索、站点卡、跳 BlueMap
- 编辑器 `/map/transit/edit`（permission ≥ 3）：线路/站点增删改、站序、版本历史与回退
- 数据层 `data/transit.py`：`data/transit.yml` 追加式多文档 YAML 版本库
- 接口 `backend/api/transit.py`：当前数据、校验、提交、历史、单版本、diff、回退

## 数据模型

```yaml
note: { zh: ..., en: ... }
lines:
  - id: l1
    name: { zh: 1号线, en: Line 1 }
    color: '#e04f5f'
    type: rail            # 望海交通系统固定为铁路
    status: open          # open / building / planned
    note: { zh: ..., en: ... }
    stations: [s_a, s_hub, s_c]
stations:
  - id: s_a
    name: { zh: 甲站, en: A }
    pos: [x, z]           # 世界坐标，整数
    y: 64                 # 可选，缺省用 map.start_y
    tags: [换乘]
    note: { zh: ..., en: ... }
```

`type` 固定为 `rail`，编辑器不再提供选择。

## 分段运营

现状 `line.status` 只能整条线设置，无法表达「一段已开通、一段建设中」。方案：

```yaml
lines:
  - id: l1
    status: open                    # 整线默认状态，兼容旧数据
    segments:                       # 可选，仅覆盖指定相邻区间
      - { from: s_hub, to: s_c, status: building }
```

- `from`/`to` 必须是 `stations` 中相邻的一对（顺序不限），同一对只出现一次
- 未列出的区间沿用 `status`
- 校验：区间必须相邻、站必须存在、状态枚举合法、不得重复；错误码仍为 `transit_invalid`（`data/transit.py` 已实现）
- 渲染：按区间拆 path，`open` 实线、`building` 长虚线、`planned` 点线；图例按整线状态
- 编辑：线路详情里按相邻站对列出状态下拉，默认「跟随整线」
- 三方合并：`segments` 按 `from|to` 归一化后做集合合并，相邻站变化时由校验拦截

## 版本库

- 每次写入只追加一个 YAML 文档，历史字节不动
- 版本 ID = `sha256(canonical({parent, data}))[:6]`
- 提交带 `base_version`，落后时三方合并；冲突 409 `transit_conflict` 带 `current`
- 200 个版本或 8 MiB 时压实并留 `.bak`；损坏尾巴启动时备份为 `transit.yml.corrupt-<时间>`
- `force` 仅 permission ≥ 4

## 权限

- 读公开；提交/回退 permission ≥ 3；`force` ≥ 4
