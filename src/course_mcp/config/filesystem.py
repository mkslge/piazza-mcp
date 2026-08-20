import os
from pathlib import Path

from .env import load_project_env


def get_root_dir() -> Path:
    """Load and validate the configured root directory for course data."""
    load_project_env()

    root_dir = os.environ.get("ROOT_DIR") or os.environ.get("ROOT_DIR_")
    if not root_dir:
        raise RuntimeError("Missing ROOT_DIR in .env or environment")

    path = Path(root_dir).expanduser().resolve()
    if not path.exists():
        raise RuntimeError(f"ROOT_DIR does not exist: {path}")
    if not path.is_dir():
        raise RuntimeError(f"ROOT_DIR is not a directory: {path}")

    return path
