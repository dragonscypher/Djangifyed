import sys
from pathlib import Path

# Ensure project root (containing auto.py) is on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
