"""Source-tree import shim for `python3 -m ai_scout`.

The installable package lives under `src/ai_scout`. This small shim lets a
fresh checkout run the CLI without an editable install while keeping packaging
metadata pointed at the real source package.
"""

from __future__ import annotations

from pathlib import Path

_src_pkg = Path(__file__).resolve().parents[1] / "src" / "ai_scout"
if _src_pkg.exists():
    __path__.insert(0, str(_src_pkg))  # type: ignore[name-defined]

__version__ = "0.1.0"

