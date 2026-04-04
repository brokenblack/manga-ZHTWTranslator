"""
history_manager.py
翻譯歷史記錄（JSON 儲存，最多保留 500 筆）
"""

import json
import sys
import time
from pathlib import Path

# 打包後存在 exe 同層目錄，開發時存在腳本同層
if getattr(sys, "frozen", False):
    _data_dir = Path(sys.executable).parent
else:
    _data_dir = Path(__file__).parent

HISTORY_PATH = _data_dir / "history.json"
MAX_ENTRIES  = 500


def _load_raw() -> list:
    if HISTORY_PATH.exists():
        try:
            with open(HISTORY_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save_raw(entries: list):
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def add_entry(original: str, translation: str, reading: str = "") -> dict:
    """
    新增一筆翻譯記錄。
    回傳加入的 entry dict。
    """
    entry = {
        "ts":          time.strftime("%Y-%m-%d %H:%M:%S"),
        "original":    original.strip(),
        "translation": translation.strip(),
        "reading":     reading.strip(),
    }
    entries = _load_raw()
    entries.insert(0, entry)          # 最新在最前
    entries = entries[:MAX_ENTRIES]   # 超過上限就截斷
    _save_raw(entries)
    return entry


def get_entries(limit: int = 100) -> list:
    """取出最近 limit 筆"""
    return _load_raw()[:limit]


def clear_history():
    _save_raw([])


def search_entries(keyword: str, limit: int = 50) -> list:
    """在原文和翻譯中搜尋關鍵字"""
    kw = keyword.strip().lower()
    if not kw:
        return get_entries(limit)
    results = []
    for e in _load_raw():
        if kw in e.get("original", "").lower() or kw in e.get("translation", "").lower():
            results.append(e)
        if len(results) >= limit:
            break
    return results
