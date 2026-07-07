#!/usr/bin/env python3
"""Start the local vault dashboard on http://localhost:8787"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dashboard.app import main

if __name__ == "__main__":
    main()
