import os
import json
import threading
from typing import Any, Dict, Optional

import database

_LOCK = threading.RLock()
_LOCALES: Dict[str, Dict[str, Any]] = {}
_DEFAULT_LANG = "en"
_LOCALES_DIR = os.path.join(os.path.dirname(__file__), "locales")


def _deep_get(d: Dict[str, Any], path: str) -> Optional[Any]:
    cur: Any = d
    for part in path.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _format(value: Any, **kwargs) -> str:
    if isinstance(value, str):
        try:
            return value.format(**kwargs)
        except Exception:
            return value
    return str(value)


def load_locales() -> None:
    global _LOCALES
    with _LOCK:
        _LOCALES = {}
        if not os.path.isdir(_LOCALES_DIR):
            return
        for filename in os.listdir(_LOCALES_DIR):
            if not filename.endswith('.json'):
                continue
            code = filename[:-5]
            try:
                with open(os.path.join(_LOCALES_DIR, filename), 'r', encoding='utf-8') as f:
                    _LOCALES[code] = json.load(f)
            except Exception:
                continue


def available_languages() -> list[str]:
    if not _LOCALES:
        load_locales()
    return sorted(_LOCALES.keys())


def get_user_language(user_id: int) -> str:
    try:
        db = database.get_database()
        doc = db.user_language_preferences.find_one({"user_id": user_id})
        if doc and isinstance(doc.get("language"), str):
            lang = doc["language"].lower()
            if lang in available_languages():
                return lang
    except Exception:
        pass
    return _DEFAULT_LANG


def set_user_language(user_id: int, language: str) -> None:
    db = database.get_database()
    db.user_language_preferences.update_one(
        {"user_id": user_id}, {"$set": {"language": language.lower()}}, upsert=True
    )


def t(user_id: Optional[int], key: str, **kwargs) -> str:
    if not _LOCALES:
        load_locales()
    lang = _DEFAULT_LANG
    if user_id is not None:
        lang = get_user_language(user_id)
    # Try user language
    text = _deep_get(_LOCALES.get(lang, {}), key)
    if text is None:
        # Fallback to default
        text = _deep_get(_LOCALES.get(_DEFAULT_LANG, {}), key)
        if text is None:
            # As last resort, return the key
            return key
    return _format(text, **kwargs)


def tr(user_id: Optional[int], key: str) -> Any:
    """Return the raw locale value (can be list/dict/str). Fallback to default and then key."""
    if not _LOCALES:
        load_locales()
    lang = _DEFAULT_LANG
    if user_id is not None:
        lang = get_user_language(user_id)
    value = _deep_get(_LOCALES.get(lang, {}), key)
    if value is None:
        value = _deep_get(_LOCALES.get(_DEFAULT_LANG, {}), key)
        if value is None:
            return key
    return value
