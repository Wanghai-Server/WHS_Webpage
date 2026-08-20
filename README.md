# WHS Webpage

望海服务器（WangHai Server）官方网站。支持中英文双语切换、深色/浅色主题，并内置完整的用户系统（注册 / 登录 / 头像 / 鉴权）。

## 项目结构

```
WHS_Webpage/
├── backend/                         # 后端 — FastAPI (Python)
│   ├── main.py                      # 主程序：生命周期、全局异常处理、辅助逻辑、路由注册
│   ├── ws_server.py                 # WS 命令服务（与 MCDR 插件通信，监听 127.0.0.1:ws_port）
│   ├── api/                         # 路由注册（按类拆分）
│   │   ├── site.py                  # 站点信息（/、/api/whs）
│   │   ├── auth.py                  # 用户认证（验证码/注册/登录/me/解锁/资料）
│   │   ├── user.py                  # 用户主页/关注/简介/设置/密码/注销/管理员
│   │   ├── avatar.py                # 头像上传/读取
│   │   ├── message.py               # 系统消息/定向消息/已读/消息管理
│   │   ├── exam.py                  # 入服考试（考生端 + 管理端）
│   │   └── server.py                # 服务器实时状态
│   ├── requirements.txt             # Python 依赖
│   └── venv/                        # Python 虚拟环境（不入库）
│
├── mcdr_connecter_plugin/           # MCDR 插件（mcdr2web：连接后端 WS 服务，包结构）
│   ├── mcdreforged.plugin.json      # 插件元数据（id/version/依赖）
│   ├── mcdr2web/                    # 插件包（官方推荐结构）
│   │   └── __init__.py              # 插件入口：WS 客户端（连接/重连/双向请求响应）
│   └── requirements.txt             # 插件 Python 依赖（websockets）
│
├── data/                            # 数据层 + 运行时数据
│   ├── config.json                  # 配置：标题后缀、hCaptcha 密钥、token 密钥（不入库）
│   ├── __init__.py                  # read_config() 读取配置
│   ├── main/
│   │   └── database/
│   │       ├── basic_database.py    # 数据库抽象基类（路径规范化、连接生命周期、CRUD 接口）
│   │       └── user_database.py     # 用户数据库（sqlite3），users 表 + 校验 + 迁移
│   ├── database/                    # 运行时 SQLite 文件（basic_user_data.db，不入库）
│   └── avatar/                      # 用户头像文件（不入库）
│
├── whs/                             # 前端 — Vue 3 + Vite
│   ├── public/                      # 静态资源
│   ├── src/
│   │   ├── App.vue                  # 根组件（标题管理）
│   │   ├── main.js                  # 入口，挂载 router / i18n
│   │   ├── style.css                # 全局样式 & CSS 变量（主题色）
│   │   ├── assets/                  # 需构建处理的资源
│   │   ├── components/              # 可复用组件
│   │   │   ├── top_navbar.vue       # 顶部导航栏（返回按钮 / 自定义导航 / 头像）
│   │   │   ├── page_footer.vue      # 底部导航栏（语言 / 主题切换）
│   │   │   ├── login.vue            # 登录表单（账密 / 邮箱验证码）
│   │   │   ├── register.vue         # 注册表单（头像 / 邮箱 / 验证码 / 密码 / hCaptcha）
│   │   │   └── message_box.vue      # 消息弹窗（占位）
│   │   ├── composables/             # 组合式函数
│   │   │   ├── useLanguage.js       # 语言切换（localStorage 持久化）
│   │   │   └── useAuth.js           # 登录态 / token / 用户信息持久化
│   │   ├── i18n/                    # 国际化配置
│   │   ├── locales/                 # 翻译文件 zh.json / en.json
│   │   ├── pages/                   # 页面组件
│   │   │   ├── home.vue             # 首页（hero + 注册弹窗）
│   │   │   ├── about.vue            # 关于
│   │   │   ├── news_platform.vue    # 新闻列表
│   │   │   ├── news_detail.vue      # 新闻详情
│   │   │   ├── login.vue            # 登录/注册页
│   │   │   ├── user.vue             # 用户中心（占位）
│   │   │   └── joinus.vue           # 加入我们（占位）
│   │   └── router/                  # 路由配置
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
│
├── start.bat                        # Windows 一键启动
├── start.sh                         # macOS / Linux 一键启动
└── README.md
```

## 功能特性

- 🌐 **中英文双语切换** — 浏览器语言自动检测，手动选择后 localStorage 持久化。
- 🌓 **深色/浅色主题切换** — 手动切换 / 跟随系统 `prefers-color-scheme`。
- 📱 **响应式布局** — 适配桌面端与移动端（≤768px）。
- 👤 **用户系统**
  - 注册：邮箱 + 邮箱验证码 + 密码 + hCaptcha 人机验证 + 头像上传；
  - 登录：账密模式（邮箱 / UID / 用户名 + 密码）或邮箱验证码模式；
  - 密码安全：前端 SHA-256 哈希，后端加盐（`salt$hash`）存储，原始密码不出浏览器；
  - 登录态：HMAC-SHA256 签名 token（JWT 风格，无状态）；
  - 头像：上传 / 读取，登录后导航栏显示头像。
- 📨 **消息中心**（占位，待接入）。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | Vue 3（Composition API + `<script setup>`） |
| 构建工具 | Vite |
| 路由 | Vue Router |
| 国际化 | vue-i18n 9 |
| 图标 | lucide-vue-next |
| 动画 | animejs |
| 3D 模型 | skinview3d（玩家模型展示与鼠标旋转，皮肤经 mc-heads 加载） |
| 人机验证 | hCaptcha（`@hcaptcha/vue3-hcaptcha`） |
| 后端框架 | FastAPI（Python） |
| 服务器 | uvicorn |
| 表单解析 | python-multipart |
| 数据库 | SQLite（标准库 `sqlite3`，无 ORM） |

## 快速启动

### 🚀 一键启动（推荐）

| 平台 | 文件 | 说明 |
|------|------|------|
| Windows | `start.bat` | 双击运行，或在终端执行 `.\start.bat` |
| macOS / Linux | `start.sh` | `chmod +x start.sh` 后 `./start.sh` |

> 首次启动前请确保已安装 [Node.js](https://nodejs.org/) 和 [Python 3](https://www.python.org/)。

### 手动启动

#### 后端

```bash
cd backend

# 创建虚拟环境（仅首次）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动（默认 http://localhost:8000）
uvicorn main:app --reload
```

#### 前端

```bash
cd whs
npm install
npm run dev        # 开发服务器（默认 http://localhost:5173）
npm run build      # 生产构建
npm run preview    # 预览生产构建
```

## 配置说明（`data/config.json`）

```json
{
    "title_suffix": {
        "zh": " - 站点中文标题后缀",
        "en": " - Site English title suffix"
    },
    "hcaptcha": {
        "site_key": "你的 hCaptcha site key（公开）",
        "secret_key": "你的 hCaptcha secret key（私密）"
    },
    "token_secret": "登录态签名密钥（私密，随机生成）",
    "ws_port": 8765
}
```

- **`token_secret`** 用于给登录 token 签名，必须保密且随机。生成方式：
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- `config.json` 已被 `.gitignore` 忽略，**部署到服务器时需要手动创建**。

### hCaptcha 注意事项

hCaptcha 的 site key 只在你配置的域名下生效。本地开发用 `localhost` 会报
`localhost detected`，需在 [hCaptcha 控制台](https://dashboard.hcaptcha.com/)
把 `localhost`（或你的自定义本地域名、生产域名）加入该 site key 的允许域名。

## API 接口（后端）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务状态 |
| GET | `/api/whs` | 站点标题后缀（双语） |
| POST | `/api/user/send_code` | 发送邮箱验证码（当前为 mock，回传 `dev_code`） |
| POST | `/api/user/register` | 注册（email + code + password + hcaptcha_response） |
| POST | `/api/user/login` | 登录（账密 / 邮箱验证码，需 hcaptcha_response） |
| GET | `/api/user/me` | 当前登录用户（需 `Authorization: Bearer <token>`） |
| POST | `/api/user/{uid}/avatar` | 上传头像（multipart，jpg/png/webp/ico，≤2MB） |
| GET | `/api/user/{uid}/avatar` | 读取头像 |
| GET | `/api/message/{user_id}` | 消息（占位） |
| GET | `/api/server/status` | 服务器实时状态（公开；后端每 5 分钟用 mcstatus 探测游戏服务器并缓存，地址在 `config.json` 的 `server` 字段配置） |
| GET | `/api/user/by_player_name/{player_name}` | 按玩家名（player_name，非 username/fullname）查 uid，301 跳转到 `/user/{uid}`（前端"成员主页跳转"用） |
| GET | `/api/user/{uid}/accounts` | 查询游戏账户（主账号 / 小号 / 各自正版标签；仅本人或管理员） |
| POST | `/api/user/{uid}/premium` | 修改主账号正版状态（premium/offline；仅本人或管理员） |
| POST | `/api/user/{uid}/alts` | 添加小号（最多两个、全局查重；仅本人或管理员） |
| DELETE | `/api/user/{uid}/alts/{alt_name}` | 注销小号（主账号不可注销；仅本人或管理员） |

错误响应统一为结构化 + 双语：

```json
{ "code": "username_exists", "message": { "zh": "用户名已被使用", "en": "Username already taken" } }
```

## 数据库结构（`users` 表）

| 列 | 类型 | 说明 |
|----|------|------|
| `uid` | INTEGER PRIMARY KEY AUTOINCREMENT | 自增且永不重复 |
| `email` | TEXT NOT NULL UNIQUE | 唯一邮箱 |
| `username` | TEXT NOT NULL UNIQUE | 唯一用户名（注册时由邮箱自动生成） |
| `fullname` | TEXT NOT NULL | 昵称 |
| `password` | TEXT NOT NULL | 加盐后的哈希（`盐$哈希`） |
| `avatar` | TEXT | 头像文件名（可空） |

## 部署说明

1. 后端：服务器上创建虚拟环境并 `pip install -r requirements.txt`。
2. 配置：在服务器 `data/` 下创建 `config.json`（含 hCaptcha secret key、随机 `token_secret`）。
3. 前端：`npm install && npm run build`，产物在 `whs/dist/`。
4. 反向代理：用 nginx / Caddy 等把 `/api/*` 转发到 FastAPI（8000），其余请求指向 `whs/dist/`。

## License

MIT License. Copyright (c) 2026 WangHai Server.
