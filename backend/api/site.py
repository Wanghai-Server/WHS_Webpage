"""站点信息路由：服务状态与站点公开配置。"""
from fastapi import APIRouter

from data import read_whs_config

router = APIRouter()


@router.get("/")
def root():
    return {"message": "Server API", "status": "OK"}


@router.get("/api/whs")
def title():
    cfg = read_whs_config()
    return {
        "title_suffix": cfg.get("title_suffix", {}),
        "hcaptcha_site_key": cfg.get("hcaptcha", {}).get("site_key", ""),
        # 非法链接统一跳转目标（站内路由路径或 http(s):// 外部链接）
        "301": cfg.get("301", ""),
    }
