#!/usr/bin/env python3
"""Run the FastAPI app using uvicorn programmatically."""
import os
import sys
from pathlib import Path

# Change to project directory
project_root = Path(__file__).parent
os.chdir(project_root)
sys.path.insert(0, str(project_root))

# Now run uvicorn
import uvicorn

if __name__ == "__main__":
    uvicorn.run("ui:app", host="127.0.0.1", port=8000, reload=True)
