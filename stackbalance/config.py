import os
from pathlib import Path


def data_dir() -> Path:
    d = Path(os.environ.get("STACKBALANCE_DATA_DIR", "./data")).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    override = os.environ.get("STACKBALANCE_DB")
    if override:
        return Path(override).resolve()
    return data_dir() / "stackbalance.db"


def backups_dir() -> Path:
    d = data_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d
