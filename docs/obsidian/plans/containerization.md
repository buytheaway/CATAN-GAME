---
tags: [catan, план, deployment]
updated: 2026-10-04
---

# Production Infrastructure Phase 1 — Docker

[[Project State]] · [[Architecture Decisions]] · [[Сервер и протокол]] · [[Точки входа]]

Status: Completed — 2026-10-04. READY FOR CHECKPOINT. Authorized scope: containerization of checkpoint hardening-phase-1 (3cd8812). Existing uncommitted map/design documentation is preserved. Operating instructions: [[Deployment]].

## Deployment audit — initial state before changes

- Actual backend: app/server_mp.py, main() → uvicorn.run("app.server_mp:app", reload=False); CATAN_HOST defaults to 0.0.0.0, CATAN_PORT to 8000. Only application route is /ws; FastAPI also exposes its automatic OpenAPI/docs routes. No health route exists yet.
- RoomManager/GameState live in one Python process. Container startup must explicitly use one worker; no horizontal replicas or persistence are introduced.
- Web: React 18, Vite 5, npm lockfile; npm ci → npm run build. Build needs the existing devDependencies, runtime needs only dist.
- App.tsx currently selects VITE_WS_URL or ws://127.0.0.1:8000/ws. web/.env and optional .env.local configure local development; production must derive ws/wss from page origin.
- Runtime dependencies: FastAPI, Uvicorn, websockets and their transitive dependencies. Existing requirements mix server, PySide and tests with lower bounds. Add a separate fully version-pinned server requirements file using the current working Python 3.12 environment; keep desktop workflow.
- Backend files: app/__init__.py, server_mp.py, net_protocol.py, resource_path.py, engine/*.py, assets/maps/*.json. Engine has no external desktop imports. Other app assets are desktop-only.
- resource_path resolves from package location, not a Windows absolute path. Preserve /app/app/assets/maps in the image. No writable gameplay files or host mounts required.
- Existing environment outside deployment: CATAN_TEST_MODE and QT_QPA_PLATFORM serve tests/desktop; legacy CATAN_DEBUG_ROLLS does not enable public debug rolls. Do not pass them into production containers.

## Implementation

1. Add backend Dockerfile with official Python slim base, pinned server dependencies, non-root user, explicit one-worker exec startup and bounded graceful shutdown.
2. Add multi-stage web Dockerfile: official Node build stage, existing npm ci/build, official Nginx runtime running as non-root on 8080.
3. Add Nginx SPA/static routing, exact /ws Upgrade proxy and exact /health HTTP proxy. No generic backend exposure or TLS.
4. Add stateless GET /health and one shared URL resolver in existing wsClient.ts, used by App and transport fallback. Preserve local development VITE_WS_URL behavior.
5. Add Compose backend/web, backend HTTP healthcheck and service_healthy dependency, only web host port (default 80, override CATAN_WEB_PORT), no mounts.
6. Add allowlist .dockerignore excluding env files, credentials, dependencies, caches, docs, tests and build artifacts.
7. Verify real build/up, browser/static assets, two players through Nginx, start/snapshots/command round trip and graceful down; record image sizes.
8. Run pytest, web tests, TypeScript and production build. No scenario rerun unless gameplay changes.
9. Update deployment instructions, Project State and deployment ADR; validate docs links and bounded runtime diff.

## Invariants and limits

Gameplay, maps, BoardView/layout/CSS, protocol/ownership/reconnect/serialization semantics stay unchanged. Docker does not persist rooms: restarting backend loses all rooms/games/tokens. No databases, bots, account system, 3D or generator.

## Verification

All implementation steps completed. Real Docker build/up and two independent headless Chrome contexts verified HTML/assets, same-origin /ws, Host/Join/Start, eight setup placements and Roll. Both clients received matching public state/tick and nine successful ACKs; private snapshot filtering remained active. /health 200, missing asset 404, SPA fallback 200, no page errors.

Both containers run non-root, without mounts; backend port is not published. pip check and nginx -t passed. docker compose down removed services/network; exit code 0 for both, plus bounded shutdown with an active WS. Images: backend 215 MB, web 93 MB (docker image ls on Docker Desktop).

Existing checks: 158 pytest passed without skips; 25 web cases passed (21 existing + four URL cases); TypeScript and production build passed after clean npm ci. Scenario suite not rerun because gameplay did not change; historical baseline 348/508.

Deployment compatibility required synchronizing the incomplete npm lockfile with dependencies already in package.json: 251 package entries added, no existing package versions changed. No tooling migration. Runtime files changed only server_mp.py, App.tsx and wsClient.ts.

Limits: Linux/amd64 Docker Desktop + local headless Chrome, no load/full-match/LAN-device/TLS testing. Room persistence, scaling and existing dev/build dependency advisories remain separate work. No commit/tag created by this task.
