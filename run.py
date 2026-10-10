"""Launcher that works from any folder:  python run.py [--port 8765] [--no-browser]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from airscroll.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
