import os
from datetime import datetime


def ensure_results_dir(path: str = "results") -> str:
    os.makedirs(path, exist_ok=True)
    return path


def result_path(base: str, ext: str = "png", folder: str = "results") -> str:
    """Return a results path with timestamp: results/{base}_{YYYYmmdd_HHMMSS}.{ext}"""
    ensure_results_dir(folder)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(folder, f"{base}_{ts}.{ext}")
