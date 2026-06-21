from __future__ import annotations

import importlib.util
import os
from pathlib import Path


def main() -> int:
    checks = [
        ("python package", importlib.util.find_spec("ai_scout") is not None),
        ("langgraph optional package", importlib.util.find_spec("langgraph") is not None),
        ("mcp optional package", importlib.util.find_spec("mcp") is not None),
    ]
    config_dir = Path(os.environ.get("AI_SCOUT_CONFIG_DIR", "~/.config/ai-scout")).expanduser()
    data_dir = Path(os.environ.get("AI_SCOUT_DATA_DIR", "~/.local/share/ai-scout")).expanduser()

    print("AI Scout local doctor")
    print(f"config_dir: {config_dir}")
    print(f"data_dir: {data_dir}")
    failed = False
    for label, ok in checks:
        status = "ok" if ok else "missing"
        print(f"{label}: {status}")
        failed = failed or not ok and label == "python package"
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

