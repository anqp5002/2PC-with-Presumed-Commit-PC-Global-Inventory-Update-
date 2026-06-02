from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TMP_DIR = PROJECT_ROOT / ".tmp"


def main() -> int:
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    base_temp = TMP_DIR / f"pytest-{timestamp}"

    env = os.environ.copy()
    env["TMP"] = str(TMP_DIR)
    env["TEMP"] = str(TMP_DIR)

    pytest_args = sys.argv[1:] or ["tests"]
    command = [
        sys.executable,
        "-m",
        "pytest",
        *pytest_args,
        "-p",
        "no:cacheprovider",
        "--basetemp",
        str(base_temp),
    ]

    print(f"Using temp directory: {base_temp}", flush=True)
    print("Running:", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=PROJECT_ROOT, env=env)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
