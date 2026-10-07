"""Yerel demo: .venv/bin/python demo_start.py (8503 portu)."""
import os
from pathlib import Path
import secrets
import sys

root = Path(__file__).resolve().parent
private = root / ".demo"
private.mkdir(mode=0o700, exist_ok=True)
password = private / "password.txt"
if not password.exists():
    with password.open("x") as handle:
        os.chmod(password, 0o600)
        handle.write(secrets.token_urlsafe(18) + "\n")
os.chdir(root)
archive = "--archive" in sys.argv[1:]
if archive:
    os.environ["ARSIV_SHARED"] = "1"
args = [sys.executable, "-m", "streamlit", "run", "app.py" if archive else "demo_app.py",
    "--server.address", "127.0.0.1", "--server.port", os.environ.get("ARSIV_PORT", "8503"),
    "--server.headless", "true", "--server.maxUploadSize", "20",
    "--server.enableStaticServing", "false", "--server.enableXsrfProtection", "true",
    "--server.fileWatcherType", "none", "--client.showErrorDetails", "false",
    "--browser.gatherUsageStats", "false"]
for origin in os.environ.get("DEMO_PUBLIC_ORIGINS", "").split(","):
    if origin.strip():
        args.extend(["--server.corsAllowedOrigins", origin.strip()])
os.execv(sys.executable, args)
