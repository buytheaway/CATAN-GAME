"""Isolated real-backend launcher for natural Chrome match acceptance.

This is test infrastructure, never a production entrypoint. No resource grants,
state edits, gameplay overrides or test-control endpoints are installed.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import urlsplit


def validate_environment(port: int) -> None:
    url = urlsplit(os.environ.get("DATABASE_URL", ""))
    if (url.scheme != "postgresql+psycopg" or url.hostname not in ("127.0.0.1", "localhost", "::1")
            or not url.path.removeprefix("/").endswith("_test")):
        raise SystemExit("Use an isolated localhost PostgreSQL database ending in _test")
    if port < 1024 or os.environ.get("CATAN_ENABLE_TEST_TOOLS", "0") != "0":
        raise SystemExit("Unprivileged localhost port and disabled Test Tools are required")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18768)
    args = parser.parse_args()
    validate_environment(args.port)
    origin = f"http://127.0.0.1:{args.port}"
    os.environ["CATAN_AUTH_ORIGINS"] = origin
    os.environ["CATAN_PERSISTENCE_MODE"] = "durable"
    os.environ["CATAN_ENABLE_TEST_TOOLS"] = "0"
    import uvicorn
    from fastapi.staticfiles import StaticFiles
    from starlette.exceptions import HTTPException
    from app import server_mp as server

    # Only server-owned randomness is controlled in the isolated test process.
    # The HTTP and WebSocket API still have no RNG/seed override or debug grant.
    from tests.full_match_support import install_natural_rng
    install_natural_rng(server)
    dist = Path(__file__).resolve().parents[1] / "dist"
    if not (dist / "index.html").is_file():
        raise SystemExit("Build the normal production frontend before acceptance")
    class ProductionStaticFiles(StaticFiles):
        """Mirror the existing Nginx SPA fallback, retaining asset/API 404s."""
        async def get_response(self, path, scope):
            try:
                return await super().get_response(path, scope)
            except HTTPException as exc:
                if exc.status_code != 404 or path.startswith(("assets/", "api/")):
                    raise
                return await super().get_response("index.html", scope)

    server.app.mount("/", ProductionStaticFiles(directory=dist, html=True), name="natural-acceptance-web")
    uvicorn.run(server.app, host="127.0.0.1", port=args.port,
                loop="app.persistence.db:selector_event_loop" if os.name == "nt" else "auto",
                proxy_headers=False, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
