import sys
from pathlib import Path

# Make `holiday_etl` importable whether pytest runs from the repo root or this folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
