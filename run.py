#!/usr/bin/env python3
"""
Kitsune for Linux launcher.
Usage:
    python3 run.py
    python3 run.py --diagnostics
    python3 run.py --settings
"""

import sys
from pathlib import Path

# Ensure kitsune package is in pythonpath
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from kitsune.main import main

if __name__ == "__main__":
    sys.exit(main())
