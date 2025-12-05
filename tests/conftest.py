import sys
from pathlib import Path

# Ensure tracker package is importable during tests
ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "tracker_app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
