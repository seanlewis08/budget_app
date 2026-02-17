"""
PyInstaller entry point for the Budget App backend.
Launches uvicorn with the FastAPI app using absolute imports.
"""

import sys
import os

# Ensure the parent directory is on the path so 'backend' is importable
app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("BUDGET_APP_PORT", 8000))
    uvicorn.run("backend.main:app", host="127.0.0.1", port=port)
