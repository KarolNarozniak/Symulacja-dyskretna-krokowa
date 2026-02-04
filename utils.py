from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os


def _base_output_dir() -> Path:
    # A writable per-user location on Windows
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "airport_lab7_outputs"
    # fallback
    return Path.home() / "airport_lab7_outputs"


def ensure_results_dir(folder: str = "results") -> Path:
    p = (_base_output_dir() / folder).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def result_path(base: str, ext: str = "png", folder: str = "results") -> str:
    out_dir = ensure_results_dir(folder)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str((out_dir / f"{base}_{ts}.{ext}").resolve())
