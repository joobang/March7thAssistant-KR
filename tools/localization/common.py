"""Shared filesystem, metadata and serialization utilities."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "localization"


def save_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
        temp_path = Path(file.name)
    os.replace(temp_path, path)


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as source:
        return json.load(source)
