import os
from pathlib import Path


PROJECT_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


def load_project_env() -> None:
    """Load unset environment variables from the project's dotenv file."""
    if not PROJECT_ENV_PATH.exists():
        return

    for line in PROJECT_ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        # Explicit process variables take precedence over local .env defaults.
        os.environ.setdefault(key, value)
