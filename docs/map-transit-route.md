# 轨交路线图技术报告（v4）

- 项目：WHS Webpage（望海服务器官网，`https://github.com/Wanghai-Server/WHS_Webpage`）
- 分支：`feat/map-transit-route`
- 核查对象：`main`（`5c7128e`）当前 `/map` 实现
- 报告日期：2026-11-22
- 需求来源：yello 第三轮 6 条修改意见（v3 已被取代，本报告为准）

---

## 0. 结论

v4 在 v3 上补了 6 件事，其中两件是结构性的：

| 维度 | v3 | v4 |
| --- | --- | --- |
| 存储写入 | 每次提交整文件重写（O(总版本数)） | **追加式多文档 YAML**（O(本次版本)）+ 定期压实 |
| 重复提交 | 会照写 | **幂等**：同内容同 ID 直接返回，不落盘；编辑器保存防抖 |
| 断点 | 1024 / 768 两个 | **统一 768px**（≥768 并排，<768 面板 + 抽屉） |
| 强制并入 | 无 | 仅 **permission ≥ 4** 可用 |
| 站点 `y` | 手动填 | **默认自动生成**（取点 / 配置兜底），可手改 |
| 取点 | 未设计 | **两端都做**：弹窗（手机抽屉）内嵌 BlueMap iframe 回填坐标 |

其余（SVG 渲染、`transit.yml` 不入库启动自建、版本 ID = SHA256 前 6 位、200 版上限、三方合并、MC 方块色板、双语、`pos` 为车站中心整数、编辑 ≥3）沿用 v3。

---

## 1. 意见 → 设计对照

| # | 意见 | 落点 |
| --- | --- | --- |
| 1 | 反复提交导致反复重写文件，I/O 压力大 | 第 4 节：追加写 + 幂等 + 压实 + 保存防抖 |
| 2 | 768 ≤ 宽 < 1024 没定义，统一以 768 为界 | 第 9.1 节：`@media (min-width: 768px)` 并排 / 否则面板 + 抽屉 |
| 3 | 版本上限 200 符合需求 | 第 4.4 节：`MAX_VERSIONS = 200` |
| 4 | 强制并入仅限 4 级权限 | 第 5.7 节、第 12 节 |
| 5 | 站点 `y` 一般自动生成，也可手动填写 | 第 3.3 节、第 10.3 节 |
| 6 | 取点：两端都做，弹窗 / 抽屉内嵌 iframe | 第 10 节 |

---

## 2. 现状

### 2.1 `/map`

- 路由 `whs/src/router/index.js:18-21`；页面 `whs/src/pages/map.vue`（822 行）。
- `viewerSrc`（`map.vue:38`）拼 BlueMap hash：`#mapId:x:y:z:150:0:1.1:0:0:perspective`。
- 后端 `backend/api/map.py` 三条接口，成员门槛 `_MEMBER_PERMISSION = 2`。
- v4 对它只加两样：页面内提示条、URL 坐标参数（`?x=&z=&y=&station=`）。

### 2.2 待清理的旧实现

| 文件 | 处理 |
| --- | --- |
| `data/transit.json` | 删除 |
| `data/transit.py` | 重写为「追加式多版本 YAML」模块 |
| `backend/api/map.py` 里的 `/api/map/transit` | 迁到 `backend/api/transit.py` |
| `whs/src/components/map_transit.vue` | 删除，改 `pages/map/transit/index.vue` + `components/transit_diagram.vue` |
| `whs/src/composables/mapTransit.js` | 删除，改 `transitLayout.js` |
| `map.vue` 的按钮 / 浮层 | 删除，改提示条 + 坐标参数 |

布局思路（方向量化、圆角、站名避让）继续用，代码重写。

---

## 3. 数据内容

### 3.1 位置与生命周期

- 路径：`data/transit.yml`（**运行时文件，不入库**）。
- 后端启动（`lifespan`）检查：不存在就用代码里的种子创建（`data/transit.py::seed_transit()`），日志打一行。
- `.gitignore` 忽略：`data/transit.yml`、`transit.yml.bak`、`*.tmp`。
- 备份：压实（重写）前把旧文件复制成 `.bak`；运维备份清单加 `data/transit.yml`。

### 3.2 `data` 段（每个版本的内容）

```yaml
note: {zh: 示意图，非等比, en: Schematic, not to scale}

lines:
  - id: l1
    name: {zh: 1号线, en: Line 1}
    color: "#2f7fe0"          # MC 染色方块色板或 HEX
    type: metro               # metro | rail | bus
    status: open              # open | building | planned
    note: {zh: ..., en: ...}  # 可选：线路提示，图例 hover 显示
    stations: [s_farm, s_hub, s_port]

stations:
  - id: s_hub
    name: {zh: 中枢站, en: Hub}
    pos: [0, 0]               # 车站中心，整数 x/z
    y: 70                     # 可选：不填时按第 3.3 节自动生成
    tags: [hub]               # 保留字段，不参与渲染逻辑
    note: {zh: 全网换乘中心, en: Network interchange}
```

### 3.3 `y` 的取值规则（意见 5）

按优先级：

1. 站点**手动**填了 `y` → 用它。
2. 站点是通过取点弹窗创建的 → 用取点时 BlueMap 给的高度（见第 10 节）。
3. 都没有 → 用 `data/config.json` 的 `map.start_y`。

接口返回时会把「实际生效的 `y`」和「来源（`explicit` / `picked` / `default`）」一起给前端，编辑器里显示「自动 70（来自取点）」这种提示，避免管理员误以为必须手填。

`y` 只影响 `/map?x=&z=&y=` 的 3D 定位高度，不影响示意图布局。

---

## 4. 存储：追加式多版本（意见 1 / 3）

### 4.1 问题

v3 的格式是 `{format, current, versions: [...]}`，**每次提交都要把包含 200 个版本的整份文件重写一遍**。按每版 30 KB 算，写一次 ≈ 6 MB，每次提交都放大成 6 MB 写 + `.bak` 再拷一份 —— 这既是磁盘 I/O，也是 SSD 写放大和备份体积。

### 4.2 方案：多文档 YAML + 追加写

`transit.yml` 改成**多个 YAML 文档**（`---` 分隔），提交时只在文件尾部追加一个新文档：

```yaml
# WHS 轨交路线图（追加式版本库，勿手改结构）
format: 1
---
id: "9f8e7d"
parent: null
created_at: "2026-11-22T13:40:00+08:00"
author: {uid: 1, name: seed}
summary: 初始化
data: {note: {...}, lines: [...], stations: [...]}
---
id: "a1b2c3"
parent: "9f8e7d"
created_at: "2026-11-22T14:05:12+08:00"
author: {uid: 12, name: ZhangZuoqian}
summary: 新增 2 号线与 3 个车站
data: {note: {...}, lines: [...], stations: [...]}
```

- 第一个文档是头部（`format`）。
- `current` = **最后一个版本文档**的 `id`，不单独存字段，少一处不一致。
- 读：`yaml.safe_load_all` 顺序解析；`GET /api/map/transit` 只取最后一个文档的 `data`。
- 写：`open(path, "a")` 追加 `---\n` + `safe_dump(doc)`，**只写本次版本**，历史一个字节都不碰。

### 4.3 写放大对比

| 场景 | v3（整文件重写） | v4（追加） |
| --- | --- | --- |
| 第 1 次提交 | 30 KB | 30 KB |
| 第 100 次提交 | ≈ 3 MB | 30 KB |
| 第 200 次提交 | ≈ 6 MB | 30 KB |
| 一天 20 次提交 | ≈ 60–120 MB 写 | ≈ 600 KB 写 |

再叠加 `.bak` 拷贝和文件系统元数据，v3 的实际写放大还要再乘 2。

### 4.4 压实（compaction）与上限（意见 3）

追加不会回收空间，所以需要偶尔重写一次，把历史裁到 200 版：

- 触发条件（任一）：版本数 > **200**（`MAX_VERSIONS`）或文件 > **8 MiB**。
- 做法：读全部文档 → 保留最近 200 版（`current` 必须保留）→ 写 `transit.yml.tmp` → `os.replace`；重写前把原文件复制成 `.bak`。
- 频率：200 版、每版 30 KB，大约**每 200 次提交**才发生一次整文件重写，平均到每次提交的写放大可以忽略。
- 也可以在运维低峰手动触发（`python -m data.transit compact`），本期不做命令，只留函数。

### 4.5 幂等与去重（同属意见 1）

- `version_id = sha256(canonical({parent, data}))[:6]`；**同内容 + 同父版本 → 同 ID**。
- 提交时先算 ID：如果 `id` 已存在于文件里（比如用户重复点保存、网络重试），**直接返回该版本，不追加、不写盘**。
- 编辑器侧再兜一层：保存按钮点击后 1 秒内禁用；页面级别不做自动保存（只有显式保存才写）。

### 4.6 崩溃安全

- 追加前记录 `size_before`；追加后重新解析最后一个文档，失败则 `truncate(size_before)` 回滚，保证文件不会留下半截文档。
- 追加不强制 `fsync`（靠 OS 缓冲 + 上面的校验回滚）；压实走 `tmp + os.replace`，任何时刻用 `os.replace` 保证原子。
- 全流程用模块级 `threading.Lock` 串行化（后端单进程）。

---

## 5. 版本、协作与冲突

### 5.1 版本 ID

```text
id = sha256(canonical({parent, data}))[:6]
```

- `canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`。
- 撞车时依次取 7、8 位，直到唯一。
- 不掺时间戳：同样内容同样父版本 → 同 ID（幂等的基础）。

### 5.2 操作

| 操作 | 行为 |
| --- | --- |
| 提交 | 追加新文档，`parent = current` |
| 回退 | 取目标版本 `data`，追加一个**新版本**（`summary: 回退到 xxxx`），不删历史 |
| 查看 | 列表（id / 时间 / 作者 / 摘要 / 线数 / 站数）+ 单版本内容 |
| 对比 | 前端对两个版本的 `data` 做结构化 diff |
| 删除 | 不提供；只有压实裁掉最老的 |

### 5.3 提交流程

1. 编辑器加载时记住 `base_version = current`。
2. 保存 `POST /api/map/transit` `{base_version, summary, data}`。
3. 后端：
   - `base_version == current` → 直接追加（201）。
   - 不相等 → `base`（起点）/ `current`（最新）/ `incoming`（提交）三方合并；成功则追加（summary 后加「（自动合并）」），失败 409。

### 5.4 合并粒度

- 顶层 `note` 字段级。
- 线路按 `id`：新增 / 删除 / 字段（`name.zh` / `name.en` / `color` / `type` / `status` / `note` / `stations`）。
- 车站按 `id`：新增 / 删除 / 字段（`name.zh` / `name.en` / `pos` / `y` / `tags` / `note`）。

### 5.5 冲突判定

| 情况 | 结果 |
| --- | --- |
| 不同对象 | 自动合并 |
| 同一对象不同字段 | 自动合并 |
| 同一对象同一字段、值不同 | 冲突 |
| 一侧删除、另一侧修改 | 冲突 |
| 同一线路 `stations` 两侧都改且结果不同 | 冲突 |
| 两侧新增同 id 且内容不同 | 冲突 |

### 5.6 冲突响应

```json
{
  "code": "transit_conflict",
  "message": {"zh": "路线图已被其他人修改", "en": "The map was modified by someone else"},
  "detail": {
    "base_version": "9f8e7d",
    "current_version": "a1b2c3",
    "conflicts": [
      {"path": "lines[l2].color", "base": "#e2554a", "current": "#f0a020", "incoming": "#2f7fe0"}
    ]
  }
}
```

编辑器弹出冲突面板：三列（我的 / 线上 / 基线），逐项选边或手填，全部解决后以 `current_version` 为新的 `base_version` 重新提交。

### 5.7 强制并入（意见 4）

- 冲突面板提供「强制用我的版本」入口，**仅 permission ≥ 4（owner）** 可见、可用。
- 服务端同样校验：`POST /api/map/transit` 带 `force: true` 时，权限不足返回 403 `transit_force_forbidden`，不写盘。
- 强制并入仍是**追加新版本**（`parent = current`，`summary` 加「（强制并入）」），旧版本保留，可回退。绝不物理覆盖历史。

### 5.8 并发安全

- 模块级 `threading.Lock` 包住「读 → 合并 → 追加/压实」。
- 追加 + 校验 + 截断回滚见第 4.6 节。
- 多进程部署（gunicorn 之类）需要文件锁，本期不做，README 注明。

---

## 6. 后端接口

新模块 `backend/api/transit.py`，`backend/main.py` 注册 `transit_router`，错误码进 `ERROR_MESSAGES` + `STATUS_BY_ERROR`。

| 方法 | 路径 | 鉴权 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/map/transit` | 公开 | 当前 `data` + `version` + `can_edit` + `can_force` |
| GET | `/api/map/transit/versions` | 公开 | 历史列表（id / 时间 / 作者 / 摘要 / 统计，不含 data） |
| GET | `/api/map/transit/versions/{id}` | ≥3 | 单版本内容（回退预览 / 对比） |
| POST | `/api/map/transit` | ≥3 | 提交；`base_version` 落后则合并，冲突 409；`force` 仅 ≥4 |
| POST | `/api/map/transit/rollback` | ≥3 | 回退到指定版本（追加新版本） |
| POST | `/api/map/transit/validate` | ≥3 | 干跑校验，不落盘 |

约定：

- `GET` 永远 200（`available: false` + `error` 表示读不出来）。
- `transit_invalid` 400（带位置）、`transit_conflict` 409（带清单）、`transit_force_forbidden` 403、`transit_unavailable` 503。
- 读缓存按 `(mtime, size)`；写成功后失效。

---

## 7. 数据层模块 `data/transit.py`

```python
TRANSIT_PATH = Path(__file__).parent / "transit.yml"
MAX_VERSIONS = 200
MAX_BYTES = 8 * 1024 * 1024

def seed_transit() -> dict                     # 种子版本（示例线 + 2 站）
def ensure_transit_file(path=None) -> None     # 启动检查并创建
def load_store(path=None) -> dict              # {format, versions: [...]}（顺序读多文档）
def load_current(path=None) -> tuple[dict, str, list[str]]   # data, version_id, warnings
def validate_data(data) -> tuple[dict, list[str]]            # 单版本校验（带位置）
def version_id(parent, data) -> str                          # SHA256 前 6 位，撞车加长
def append_version(doc, path=None) -> None                   # 追加 + 校验 + 失败截断
def submit(data, *, base_version, author, summary, force=False, path=None) -> dict
def rollback(target_id, *, author, summary, path=None) -> dict
def compact(path=None, keep=MAX_VERSIONS) -> dict            # 重写并裁到 200 版
def diff_versions(a, b) -> list[dict]
def merge_three_way(base, current, incoming) -> tuple[dict, list[dict]]
```

- 校验失败抛 `TransitConfigError`（带位置）。
- 压实：`.bak` → `tmp` → `os.replace`。

---

## 8. 渲染（SVG）

### 8.1 画什么

```html
<svg viewBox="...">
  <g class="lines">
    <path :d="line.path" :stroke="line.color" :stroke-dasharray="dash" />
  </g>
  <g class="stations">
    <circle r="6" /><circle v-if="transfer" r="10" fill="none" />
    <text />
  </g>
</svg>
```

- 线路 `<path>`：直线 `L`，转角 `Q` 削圆（半径 28）。
- 在建 / 规划：`stroke-dasharray="9 7"`。
- 站点：`<circle>`，换乘站加一圈环；站名 `<text>` + `paint-order: stroke` 描边。
- 缩放平移：改 `viewBox`。

### 8.2 布局

1. 方向 = 真实坐标差，量化到 **15° 网格**。
2. 站间距固定（76），示意图非等比，图例常驻说明。
3. 换乘跳点：枚举 24 个方向找两段都落网格、总长最短的拐点。
4. 圆角：拐点前后各 28 取切点，`Q` 连控制点。
5. 站名四向避让 + 矩形碰撞。
6. 坐标全同 / 单站线路 → 退化列表，不白屏。

---

## 9. 编辑器 `/map/transit/edit`

### 9.1 布局（意见 2：统一 768px）

**≥ 768px（桌面 + 平板，同一套）**：并排三栏

```text
┌──────────────┬────────────────────────┬──────────────────┐
│ 元素面板      │  预览（SVG）            │  详细信息         │
│ 线路 / 站点切换│  点选元素 → 选中        │  选中时才显示      │
│ + 新建（就地） │                        │  表单 / 站序 / 操作 │
└──────────────┴────────────────────────┴──────────────────┘
```

- 没有选中时右栏整列隐藏（预览变宽）。
- 新建：左侧列表内联出一行表单，就地创建。

**< 768px（手机）**：顶部面板 + 预览 + 抽屉

```text
┌──────────────────────────────┐
│ 顶部元素面板（横向 tabs + 滑动列表）│
├──────────────────────────────┤
│ 预览（SVG，可缩放平移）            │
└──────────────────────────────┘
   点选 → 底部抽屉（≤80vh，内部滚动）
   新建 → 抽屉表单
```

- 断点只有一个：`@media (max-width: 767px)`；768–1023 与 1024+ 同属并排布局，只是栏宽按比例缩（`grid-template-columns: minmax(220px, 300px) 1fr minmax(280px, 360px)`）。

### 9.2 功能

**线路**：新建 / 删除（只解绑，不删站）/ 双语名 / 颜色（色板 + HEX）/ `type` / `status` / 线路 `note` / 排序 / 站序编辑。

**站点**：新建 / 编辑 / 删除（被引用先提示解绑）/ 从站点库加到线路。

**保存链路**：校验 → 提交（带 `base_version`）→ 冲突面板（含 owner 的「强制并入」）→ 历史与回退。

**保护**：未保存离开拦截；「还原」重新 GET；保存按钮 1 秒防抖。

### 9.3 双语

数据 `name` / `note` 为 `{zh, en}`；界面文案全走 `locales` 的 `transit.*`；字段编辑带 zh / en 切换。

### 9.4 权限

`permission ≥ 3` 进入编辑；「强制并入」≥ 4。

---

## 10. 取点（意见 6）

### 10.1 交互

- 编辑器里站点的坐标字段旁有「从地图取点」按钮。
- 桌面：居中弹窗（约 1000×640，可拖拽/最大化）；手机：底部抽屉（≤ 90vh，可上下拖）。
- 弹窗内容：内嵌 `<iframe src="/map3d/#world:x:y:z:...">`（沿用现有 BlueMap 入口与鉴权 Cookie），底部一行说明 + 「用这个位置」按钮。

### 10.2 坐标来源（实现前先验证）

同源 iframe，两条路取坐标：

1. **优先：BlueMap 的 JS 接口**。BlueMap 网页端在同源 iframe 里可以访问到它的 viewer 对象（如 `iframe.contentWindow.bluemap?.mapViewer`），用「屏幕点 → 世界坐标」的投影方法取精确点击位置。实现前先在真机确认暴露了哪些方法（P4 第一件事），确认不了就走方案 2。
2. **兜底：读 hash 的相机坐标**。用户把视角移动到目标位置后，BlueMap 会把当前相机 `x,y,z` 写进自己的 URL hash；编辑器监听 iframe 的 `hashchange`（同源可读 `contentWindow.location.hash`），解析出 `x / z` 作为水平坐标、`y` 作为高度初值。弹窗里明确标注「取的是当前视角中心，请在表单里核对」，避免用户误以为点哪取哪。

两条路都失败时（比如 BlueMap 没部署）→ 弹窗显示「地图不可用，请手动填写坐标」，退回表单手输。

### 10.3 与 `y` 的关系（意见 5）

- 取点得到的 `y` 直接写入站点 `y`（来源标记 `picked`）。
- 取不到高度时先留空，接口返回时按第 3.3 节规则用 `start_y` 兜底，编辑器显示「自动」。
- 用户随时可以手改 `y`，改成手填后来源变 `explicit`。

### 10.4 权限与复用

- 取点沿用 BlueMap 的成员门槛（permission ≥ 2）：编辑器本身 ≥3，所以正常管理员都能用；游客不涉及。
- iframe 打开时带上 `?utm=transit-pick` 之类标记（可选），方便 BlueMap 侧日志区分。

---

## 11. 页面与路由

| 路径 | 页面 | 权限 |
| --- | --- | --- |
| `/map` | BlueMap（原有）+ 提示条 + 坐标参数 | 成员 |
| `/map/transit` | 只读路线图 | 公开 |
| `/map/transit/edit` | 编辑器 | ≥3 |

- `/map` 提示条：「按线路找地方？看看轨交路线图 →」，内联，不进导航 / 页脚 / 用户下拉。
- 点车站「在 3D 地图中查看」→ `/map?x=&z=&y=&station=`，`/map` 定位后清掉 query。
- 路线图页面不加载 BlueMap（取点弹窗例外，它是另一个页面打开的独立 iframe）。

---

## 12. 权限总表

| 能力 | 门槛 |
| --- | --- |
| 查看 `/map/transit` | 公开 |
| 跳转 `/map` 定位 | ≥2 |
| 编辑 `/map/transit/edit` | ≥3 |
| 强制并入冲突 | **≥4** |

---

## 13. 性能与 I/O

- 提交写放大：每次仅追加一个版本（≈30 KB），第 200 次提交也是 30 KB（v3 是 6 MB）。
- 压实：每 200 次提交一次全量重写（≈6 MB），平均每次 +30 KB。
- 幂等：重复保存不写盘。
- 读：`GET` 解析整文件（200 版 ≈ 6 MB YAML），按 `(mtime, size)` 缓存，常态只解析一次；如果以后版本变多，再改成「只读最后 N KB + 索引」。
- 渲染：300 站 / 20 线 ≈ 700 个 SVG 元素，布局在 `computed` 里一次算完。

---

## 14. 测试与 CI

1. **数据层**（临时目录）：
   - `ensure_transit_file` 建种子；重复调用不覆盖。
   - 追加写：提交后文件**只增长、前面字节不变**（比较前缀哈希）。
   - 幂等：同内容同父提交两次 → 只有一个版本、第二次不写盘（文件大小不变）。
   - `version_id` 6 位 hex、同内容同 ID、改内容变 ID。
   - 三方合并：不同对象 / 不同字段自动合并；同字段不同值、一删一改、站序冲突 → 冲突。
   - `force` 仅 ≥4：接口层测 403（数据层函数不判权限，权限在路由）。
   - 回退：追加新版本且内容等于目标。
   - 压实：201 版后裁到 200，`current` 保留；`.bak` 生成。
   - 追加失败回滚：模拟写坏字节 → 截断回原长、文件仍可解析。
   - 非法数据被拒绝且文件不变。
2. **后端**：`GET /api/map/transit` 200；`POST` 未登录 401；`POST validate` 未登录 401；`GET versions` 200。
3. **前端**：`npm run build`。
4. **MCDR**：无改动。

---

## 15. 分期

| 期 | 内容 | 交付 |
| --- | --- | --- |
| P1 | 追加式多版本数据层（含压实 / 幂等 / 合并）+ `backend/api/transit.py` + CI 用例 | 接口能提交、合并、回退 |
| P2 | `/map/transit` 只读页（SVG）+ 图例 / 搜索 / 站点卡 + `/map` 提示条与坐标跳转 | 能看、能跳 3D |
| P3 | 编辑器（768 断点双布局、就地创建、色板、双语、冲突面板 + 强制并入、历史） | 管理员能改线路 |
| P4 | 取点弹窗 / 抽屉（iframe + 坐标回填）、版本对比视图 | 闭环 |

---

## 16. 待确认

1. 取点方案 1 依赖 BlueMap 暴露的 JS 接口，需要真机验证；如果只有 hash 兜底，能否接受「取视角中心」而不是「精确点击点」？
2. 修复 / 强制并入后的 `summary` 文案格式（现在是「（自动合并）」「（强制并入）」「回退到 xxxx」）。
3. 压实除了「200 版 / 8 MiB」，要不要加一条「每天凌晨也压一次」？

---

## 17. 验收清单

- [ ] `data/transit.yml` 不在 Git 里；删掉后重启后端自动重建
- [ ] 连续提交 10 次，文件只追加（前面的字节不变），总大小 ≈ 10 × 单版本
- [ ] 重复点保存不会产生新版本（幂等）
- [ ] 201 版后压实到 200，`.bak` 存在，`current` 仍在
- [ ] `/map/transit` 游客可看；线路直线 + 圆角；在建 / 规划虚线
- [ ] 点站出卡，「在 3D 地图中查看」跳到 `/map` 并定位
- [ ] `/map` 有提示条，导航无入口
- [ ] 768–1023 宽度下编辑器是并排三栏（不是抽屉）；<768 才是面板 + 抽屉
- [ ] 新建元素：桌面就地、手机抽屉表单
- [ ] 色板 5 类 × 16 色 + HEX
- [ ] 版本 ID 6 位、可回退、可看历史
- [ ] 不同线路并发改自动合并；同字段冲突 409；≥4 可强制并入，<4 返回 403
- [ ] 取点：桌面弹窗 / 手机抽屉内嵌 BlueMap，能回填 `x/z`，`y` 自动带上且可手改
- [ ] 双语齐全；编辑器权限 <3 进不去
- [ ] 四层 CI 全绿；README 的 API 条数、功能、结构、部署同步更新

---

## 18. 核对依据

- `whs/src/router/index.js:18-21`：`/map` 路由。
- `whs/src/pages/map.vue:38`：3D hash；`:166` 配置加载；`:242` 工具区；`:286` 画布容器。
- `backend/api/map.py:26`：成员门槛；`:52` 配置读取；`:118` 探活。
- `backend/main.py`：`ERROR_MESSAGES`、`lifespan`（启动钩子）、`include_router` 区。
- `data/exam.py`：YAML 读写 + 原子替换的现有写法。
- `whs/src/locales/zh.json` 的 `map.*`：现有 13 个键（v4 新增 `transit.*` 与提示条文案）。
