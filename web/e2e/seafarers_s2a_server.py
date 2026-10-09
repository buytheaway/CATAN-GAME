"""Production app/dist on an explicitly disposable PostgreSQL browser database."""
import os
from pathlib import Path

from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import make_url

from app.server_mp import app

url = make_url(os.environ["DATABASE_URL"])
if not url.database.endswith("_test"):
    raise RuntimeError("S2A browser acceptance requires an isolated *_test database")

app.mount("/", StaticFiles(directory=Path(__file__).resolve().parents[1] / "dist", html=True))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=18766, workers=1,
                loop="app.persistence.db:selector_event_loop" if os.name == "nt" else "auto")
