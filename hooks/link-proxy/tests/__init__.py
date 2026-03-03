"""Link-proxy test package — adds hook directory to sys.path."""

import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent.parent
if str(HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(HOOK_DIR))
