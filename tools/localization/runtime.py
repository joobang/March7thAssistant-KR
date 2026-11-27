"""Scoped game-screen text rules independent of translated application UI."""

from __future__ import annotations

import os
import unicodedata
from functools import lru_cache
from pathlib import Path

from .common import DATA, load_json


SUPPORTED = ("zh_CN", "ko_KR")


def game_language(config=None) -> str:
    language = os.environ.get("M7A_GAME_LANGUAGE")
    if language is None and config is not None:
        getter = getattr(config, "get_value", None)
        language = getter("game_language", "zh_CN") if callable(getter) else getattr(config, "game_language", "zh_CN")
    language = language if isinstance(language, str) and language else "zh_CN"
    if language not in SUPPORTED:
        raise ValueError(f"Unsupported game language: {language}")
    return language


def normalize(text: str) -> str:
    """Normalize typography without removing meaningful Korean word spacing."""
    return " ".join(unicodedata.normalize("NFKC", text).split())


@lru_cache(maxsize=8)
def _verified_strings(path: str, stamp: int):
    payload = load_json(Path(path), {})
    return payload.get("entries", payload)


def strings(data: Path = DATA) -> dict:
    path = data / "verified/strings.json"
    return _verified_strings(str(path), path.stat().st_mtime_ns if path.exists() else -1)
