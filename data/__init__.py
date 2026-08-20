from .main import *

import json
import os
import secrets
from pathlib import Path

# 配置目录：锚定到本文件所在 data/ 目录，与运行时工作目录无关。
CONFIG_DIR = Path(__file__).resolve().parent


def _resolve_path(path: str | Path) -> Path:
    """相对路径基于 CONFIG_DIR 解析；绝对路径原样返回。"""
    p = Path(path)
    return p if p.is_absolute() else CONFIG_DIR / p


def _secret_default_config() -> dict:
    """私密默认配置（config.json）：hCaptcha secret + SMTP 凭据 + 随机 token_secret + 游戏服务器地址。"""
    return {
        "hcaptcha": {"secret_key": ""},
        "smtp": {"username": "", "password": ""},
        "token_secret": secrets.token_hex(32),
        # 游戏服务器地址（后端用 mcstatus 探测实时状态，供 /api/server/status 使用）
        "server": {"host": "h1.getmc.cn", "port": 31410, "timeout": 5},
        # MCDR 插件通信的 WS 服务端口（仅监听环回地址 127.0.0.1）
        "ws_port": 8765,
    }


def _public_default_config() -> dict:
    """公开默认配置（whs_config.json）：标题后缀 + hCaptcha 公钥 + SMTP 服务器信息 + 301 跳转。"""
    return {
        "title_suffix": {
            "zh": " - 一个集生电、轨交、建筑于一体的自由、开放Minecraft服务器",
            "en": " - A free and open Minecraft server that integrates redstone, rail transit, and architecture",
        },
        "hcaptcha": {"site_key": ""},
        "smtp": {
            "host": "localhost",
            "port": 2000,
            "sender": "noreply@whs.local",
            "sender_name": {"zh": "望海服务器", "en": "WHS"},
            "use_ssl": False,
        },
        # 非法链接（不存在的路由）统一跳转目标：
        # 以 http(s):// 开头视为外部链接，否则视为站内路由路径；为空则跳转根路由 /。
        "301": "",
    }


def create_default_config(path: str | Path = "config.json", config: dict | None = None) -> None:
    """把默认配置写入指定路径。

    :param path: 配置文件路径，相对路径基于 data/ 目录；默认 "config.json"。
    :param config: 要写入的配置内容；为 None 时使用私密默认配置。
    """
    try:
        config_path = _resolve_path(path)
        content = config if config is not None else _secret_default_config()
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=4, ensure_ascii=False)
    except Exception as exc:
        print(f"[config] create_default_config 失败: {exc}", flush=True)


def read_config(path: str | Path = "config.json", default_config: dict | None = None) -> dict:
    """读取配置；文件不存在时先用 default_config 创建。

    :param path: 配置文件路径，相对路径基于 data/ 目录；默认 "config.json"。
    :param default_config: 文件缺失时写入的默认配置；为 None 时使用私密默认配置。
    """
    try:
        config_path = _resolve_path(path)
        if not os.path.exists(config_path):
            create_default_config(config_path, config=default_config)
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def read_whs_config() -> dict:
    """读取前端公开配置（whs_config.json）：标题后缀 + hCaptcha 公钥。"""
    return read_config("whs_config.json", default_config=_public_default_config())
