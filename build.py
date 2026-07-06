#!/usr/bin/env python3
"""
Build script for Database Manager.
Creates venv, installs dependencies, and builds single-file executable via build.spec.
"""

import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
VENV_DIR = PROJECT_DIR / "venv"
DIST_DIR = PROJECT_DIR / "dist"

REQUIREMENTS = [
    "PySide6>=6.11.0",
    "psycopg2-binary>=2.9.0",
    "mysql-connector-python>=8.0.0",
    "pymssql>=2.2.0",
    "sqlparse>=0.5.0",
    "pyinstaller>=6.0.0",
]


def run(cmd):
    print(f"  {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=PROJECT_DIR)


def create_venv():
    if VENV_DIR.exists():
        return
    print("Creating virtual environment...")
    run([sys.executable, "-m", "venv", str(VENV_DIR)])


def python():
    return str(VENV_DIR / "bin" / "python")


def pip():
    return str(VENV_DIR / "bin" / "pip")


def install_deps():
    print("Installing dependencies...")
    run([pip(), "install", "--upgrade", "pip"])
    for req in REQUIREMENTS:
        run([pip(), "install", req])


def build():
    print("Building executable via build.spec...")
    run([python(), "-m", "PyInstaller", "build.spec", "--noconfirm", "--clean"])

    binary = DIST_DIR / "database-manager"
    if binary.exists():
        binary.chmod(0o755)
        print(f"\nBuild complete: {binary}")
        print(f"Size: {binary.stat().st_size / 1024 / 1024:.1f} MB")
    else:
        print("Build failed: binary not found")
        sys.exit(1)


def main():
    create_venv()
    install_deps()
    build()


if __name__ == "__main__":
    main()
