"""
PyInstaller entry point for the Budget App backend.
Launches uvicorn with the FastAPI app object directly (not as a string)
so it works inside the PyInstaller bundle where module discovery differs.
"""

import sys
import os

# ── SSL certificate fix for PyInstaller ──
# In a frozen (PyInstaller) build, Python can't find the system CA bundle.
# We ship certifi's cacert.pem as bundled data and point SSL at it.
if getattr(sys, 'frozen', False):
    _cert_file = os.path.join(sys._MEIPASS, 'certifi', 'cacert.pem')
    if os.path.isfile(_cert_file):
        os.environ.setdefault('SSL_CERT_FILE', _cert_file)
        os.environ.setdefault('REQUESTS_CA_BUNDLE', _cert_file)
        print(f"[ssl] CA bundle set to {_cert_file}", flush=True)
    else:
        print(f"[ssl] WARNING: cacert.pem not found at {_cert_file}", flush=True)

# Ensure the parent directory is on the path so 'backend' is importable
app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

import uvicorn
from backend.main import app

if __name__ == "__main__":
    port = int(os.environ.get("BUDGET_APP_PORT", 8000))
    uvicorn.run(app, host="127.0.0.1", port=port)
