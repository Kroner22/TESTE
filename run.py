"""Bootstrap: load .env into os.environ, then start uvicorn."""
import os, sys
from pathlib import Path

# Load .env into os.environ so providers can find API keys via os.getenv
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    import dotenv
    dotenv.load_dotenv(env_path, override=True)
    print(f"[run.py] Loaded {env_path}")
else:
    print(f"[run.py] WARNING: {env_path} not found")

from backend.app.main import app

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")
