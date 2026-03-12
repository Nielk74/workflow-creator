#!/usr/bin/env python3
"""
Installs workflow-creator to ~/.config/opencode/workflow-creator/

Copies scripts/ and agents/ so the skill can reference them at a stable path.

Usage:
    python install.py
"""

import shutil
import sys
from pathlib import Path

INSTALL_DIR = Path.home() / ".config" / "opencode" / "workflow-creator"
SKILL_DIR = Path(__file__).parent.parent


def main():
    print(f"Installing workflow-creator to {INSTALL_DIR}")

    for subdir in ["scripts", "agents", "references"]:
        src = SKILL_DIR / subdir
        dst = INSTALL_DIR / subdir
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"  Copied {subdir}/")

    print("\nDone. Scripts available at:")
    print(f"  {INSTALL_DIR / 'scripts'}")
    print("\nAdd this to your SKILL.md references or use the full path in commands.")


if __name__ == "__main__":
    main()
