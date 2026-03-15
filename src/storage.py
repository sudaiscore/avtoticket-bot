import json
import os
from typing import Dict
from src.models import Trip
from src.config import logger

STATE_FILE = "state.json"

def load_state() -> Dict[str, Trip]:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {k: Trip(**v) for k, v in data.items()}
    except json.JSONDecodeError as e:
        logger.error(f"State fayli buzilgan (JSON error): {e}. Yangidan shakllantiriladi.")
        return {}
    except Exception as e:
        logger.error(f"State faylini o'qishda kutilmagan xatolik: {e}")
        return {}

def save_state(state: Dict[str, Trip]):
    temp_name = f"{STATE_FILE}.tmp"
    try:
        data = {k: v.model_dump() for k, v in state.items()}
        with open(temp_name, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        os.replace(temp_name, STATE_FILE)
    except Exception as e:
        logger.error(f"State faylini saqlashda xatolik yuz berdi: {e}")
    finally:
        if os.path.exists(temp_name):
            try:
                os.remove(temp_name)
            except OSError: pass