from .main import *

import json
from pathlib import Path

def read_config() -> dict:
    try:
        config_path = Path(__file__).with_name("config.json")
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}