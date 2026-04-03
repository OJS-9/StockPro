#!/usr/bin/env python3
"""CI smoke check: import all application modules under src/."""
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def main() -> int:
    packages = []
    for py in SRC.rglob("*.py"):
        rel = py.relative_to(SRC)
        if rel.name == "__init__.py":
            mod = ".".join(rel.parent.parts) if rel.parent.parts else ""
        else:
            parts = list(rel.with_suffix("").parts)
            mod = ".".join(parts)
        if not mod or mod.endswith(".__init__"):
            continue
        packages.append(mod)

    failed = []
    for mod in sorted(set(packages)):
        try:
            importlib.import_module(mod)
        except Exception as e:
            failed.append((mod, e))

    if failed:
        for mod, err in failed:
            print(f"FAIL {mod}: {err}", file=sys.stderr)
        return 1
    print(f"OK: {len(set(packages))} modules imported")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
