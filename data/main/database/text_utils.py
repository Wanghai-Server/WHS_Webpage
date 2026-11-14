"""数据库层共用的纯文本处理工具。"""

import re

# MC 风格 § 颜色 / 格式代码（与前端 composables/markdown/colorCodes.js 保持一致）：
# - §0–§f 16 色；§#RRGGBB 扩展 HEX；§l/§o/§n/§m 格式；§r 复位。
# 未知的 § 组合不匹配，保持原样（与渲染器行为一致）。
_MC_CODE_RE = re.compile(r"§#(?:[0-9a-fA-F]{6})|§[0-9a-fA-FlmnorLMNOR]")


def strip_mc_color_codes(text: str) -> str:
    """移除 MC 风格 § 代码，用于标题 / 摘要 / 搜索片段等纯文本展示。"""
    if not isinstance(text, str):
        return text
    return _MC_CODE_RE.sub("", text)
