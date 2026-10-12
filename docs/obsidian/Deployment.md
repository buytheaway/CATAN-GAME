---
tags: [catan, deployment, docker]
updated: 2026-10-12
---

# Deployment

[[Project State]] · [[Точки входа]] · [[Сервер и протокол]] · [[Architecture Decisions]] · [[plans/containerization]]

Production Infrastructure Phase 1 добавила Docker Compose; Persistence 1B — durable PostgreSQL/recovery; Auth Phase 1 — account sessions/ownership. Проверено 2026-10-07 на Docker Desktop Linux containers, Windows host. Это production-like запуск с persistence/accounts, без собственного TLS termination; публичное развёртывание требует HTTPS и operational hardening.

## Frontend public assets

`deploy/web.Dockerfile` copies `web/public/` into the build stage before Vite build. This includes the finalized eight `models/terrain/*.glb` files in Nginx's production static output; Blender sources under docs are not deployment inputs. Verified **2026-10-07** with the normal Compose stack: backend/PostgreSQL healthy, HTTP/auth bootstrap/WS hello passed in Chrome, all eight GLB responses have valid headers and match source SHA-256. No service/port/proxy architecture changes.

## Account cookies and HTTPS — Auth Phase 1

Compose passes CATAN_AUTH_MODE (default **production**) and CATAN_AUTH_ORIGINS (default empty). Production registration/login require an exact configured HTTPS Origin; cookie is Secure/HttpOnly/SameSite=Lax/Path=/, max-age 30 days. Empty origins fail closed for auth mutations/cookie WS. Do not deploy development mode publicly. Existing same-origin plain-HTTP guest play remains possible independently of account auth. PostgreSQL stores users/session hashes/seat ownership; migration f1a001 upgrades existing guest schema without deleting room/match/head/token data. One backend worker remains mandatory.

Explicit local HTTP example (PowerShell):

```powershell
$env:CATAN_AUTH_MODE = 'development'
$env:CATAN_AUTH_ORIGINS = 'http://localhost,http://127.0.0.1'
docker compose up --build
```

Only development sets Secure=false. .env.example documents this local profile. For production use CATAN_AUTH_MODE=production and CATAN_AUTH_ORIGINS=https://your-domain (exact port if nonstandard, no trailing slash), with HTTPS termination in front of the existing Nginx. No insecure production cookie fallback, wildcard CORS or permissive Origin. TLS certificate provisioning/public deployment was not performed in this phase.

Nginx already proxies /api and /ws; Set-Cookie/Cookie/Origin pass unchanged, no auth token/password in URL or access-log body. Auth HTTP limits bodies to 4 KiB inside the existing 16 KiB proxy ceiling. Vite now proxies both /api and /ws to the configured backend, default 127.0.0.1:8000; browser default WS is page-origin /ws. For local Python/Vite auth set development plus allowed http://localhost:5173/http://127.0.0.1:5173 origins. Keep account HTTP/WS on the same site; explicit foreign/manual WS remains guest scope.

Dependencies: only argon2-cffi 25.1.0 and its pinned bindings/CFFI/pycparser were added; backend Docker copies app/auth. No new services/ports/worker/JWT/framework. Auth rate limits are process-local (register 5/min, login 15/min/peer, global 5× each). The original Nginx shared-peer defect is addressed by SEC-04 below; this remains a single-worker limit, not a distributed brute-force/load solution.

## Trusted proxy and auth budgets — SEC-04

Uvicorn's original default trusted only loopback, so Docker Nginx's address became every user's `request.client.host`. Real isolated reproduction: client A (`172.24.0.5`) received 15 input refusals then 429; different client B (`172.24.0.6`) immediately received 429, with Nginx at `172.24.0.4`. Health remained 200.

[compose.yaml](../../compose.yaml) now connects web/backend through a dedicated `proxy` bridge. Defaults: subnet **172.30.250.0/29**, web **172.30.250.2**, backend **172.30.250.3**. PostgreSQL stays on the original default network with backend; web cannot directly reach it. Existing named DB volume, services, published web port and single worker remain. Neither backend nor PostgreSQL has a host port. Both proxy endpoints reserve addresses so backend cannot dynamically claim the proxy's trusted address before web starts.

Compose sets **FORWARDED_ALLOW_IPS to exactly the web address**, not `*`, loopback, a Docker subnet or service DNS name. Nginx overwrites X-Forwarded-For with `$remote_addr` on API/WS/health and X-Forwarded-Proto with `$scheme`; client-supplied chains are not authoritative. Uvicorn authenticates the connecting peer and updates ASGI client/scheme. [auth/routes.py](../../app/auth/routes.py) reads only that ASGI peer and canonicalizes IPv6/IPv4-mapped addresses. Login 15/min, register 5/min, global 5× caps/window/bucket bound/Argon concurrency are unchanged. Cookie, Origin/CSRF, ownership, F1 publication and persistence do not derive authority from IP.

Standalone backend image defaults to **empty FORWARDED_ALLOW_IPS**. `python -m app.server_mp` explicitly uses empty trust, even if the shell exports `*`: localhost/Vite development keeps HTTP/WS working but direct clients cannot select IP via headers. A separate operator-managed reverse-proxy launch must configure its own exact trusted peer through Uvicorn CLI; do not use unrestricted trust.

If the reserved subnet conflicts with a local network, configure **CATAN_PROXY_SUBNET, CATAN_PROXY_IP and CATAN_BACKEND_PROXY_IP together**, with two distinct addresses inside that subnet. Invalid/conflicting Docker IPAM fails startup; it never switches to broad trust or changes the database. [tests/persistence.compose.yaml](../../tests/persistence.compose.yaml) uses separate 172.30.251.0/29 (.2 proxy/.3 backend) so normal and test projects can coexist. Extra simultaneous test projects need their own non-overlapping subnet too. Docker daemon administrators are inside the trust boundary.

Nginx accepts IPv4/IPv6 clients; upstream Docker DNS is deliberately IPv4, keeping the trusted peer exact. Normal Compose does not enable IPv6 networking automatically. The isolated acceptance network enables IPv6 only for testing. Clients behind the same NAT still share an IP budget. Additional external CDN/LB/TLS reverse-proxy hops need an explicit Nginx trusted-real-IP policy; arbitrary incoming forwarding headers remain ignored. Global protective caps are still shared, and budgets reset with the process.

Evidence: [test_auth_proxy.py](../../tests/test_auth_proxy.py), opt-in real [test_auth_proxy_docker.py](../../tests/test_auth_proxy_docker.py), and [[Project State#Current verification and status]]. Actual Docker acceptance uses disposable `_test` PostgreSQL/accounts and three separate client containers, real Nginx/Uvicorn IPv4 and IPv6, independent login/register budgets, forged forwarding, direct internal backend connections, login/cookies, account Continue, guest reconnect and Origin refusals. The normal user stack/volume is untouched. Primary configuration references: [Uvicorn 0.40 proxy settings](https://github.com/Kludex/uvicorn/blob/0.40.0/docs/settings.md#http), [Compose networks/IPAM](https://docs.docker.com/reference/compose-file/networks/), [Nginx header replacement](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header).

Repeat only in an explicit disposable project, using [auth_proxy.compose.yaml](../../tests/auth_proxy.compose.yaml). This overlay forces a local `_test` database, intentionally public synthetic credentials, empty external DATABASE_URL and localhost test ports; it must never be applied to `catan-game` or a user volume. The example env file avoids implicitly loading private `.env` values. Existing project data is not reset.

```powershell
docker compose --env-file .env.example -p catan-sec04-test -f compose.yaml -f tests/auth_proxy.compose.yaml up --build -d --wait
$env:CATAN_PROXY_TEST_PROJECT = 'catan-sec04-test'
python -B -m pytest tests/test_auth_proxy.py tests/test_auth_proxy_docker.py -p no:cacheprovider
docker compose --env-file .env.example -p catan-sec04-test -f compose.yaml -f tests/auth_proxy.compose.yaml stop
```

Windows `RUN_SERVER.bat` installs `requirements-server.txt`, including persistence and Argon2 dependencies. The existing desktop/test `requirements.txt` is separate; it is not the server runtime lock.

## Room creation admission — SEC-03

Implemented/focused-tested **2026-10-12**. [room_admission.py](../../app/room_admission.py) loads positive integer settings at RoomManager startup. [compose.yaml](../../compose.yaml) and [.env.example](../../.env.example) expose the same defaults; changing settings requires backend restart. There is no client override.

| Configuration | Default | Meaning |
| --- | ---: | --- |
| CATAN_ROOM_CREATE_LIMIT | 20 | Accepted creations per originating IP during the rolling window |
| CATAN_ROOM_CREATE_WINDOW_SECONDS | 600 | Rolling window in seconds; includes rooms already started/closed |
| CATAN_ROOM_CREATE_LOBBIES_PER_IP | 20 | Concurrent lobby rooms originally created from that IP; offline rooms still count |
| CATAN_ROOM_CREATE_LOBBIES_GLOBAL | 1000 | All durable rooms with status lobby, including NULL legacy origins and rooms not loaded into RAM |
| CATAN_ROOM_CREATE_TRACKING_CAPACITY | 4096 | Explicit memory mode only: maximum unexpired creation records across origins; refuse instead of evicting live budgets |

Guests/accounts share the canonical SEC-04 ASGI peer budget. IPv4-mapped spellings normalize; unrelated IPv4 and IPv6 addresses remain separate IPs. NAT households share generous configurable budgets; joining, reconnect, account Continue, start and rematch do not consume a creation budget. IP/username/account is not interchangeable with seat authorization. Additional CDN/LB trust still needs the explicit SEC-04 policy; arbitrary forwarding remains ignored.

Migration **sec03a001** adds nullable `rooms.creation_peer_hash` and `(creation_peer_hash, created_at)` index. No backfill, snapshot/VP/ruleset/result rewrite or data deletion. The internal unsalted digest avoids storing a new raw-IP string, but is linkable/guessable and is **not anonymization**; neither digest nor originating IP is published in room/match/Continue DTOs. Existing rooms with unknown origin count globally; per-origin historical consumption cannot be reconstructed safely.

Final migration check **2026-10-12**: Alembic has one head, `sec03a001`, following `f2a001`. Normal backend lifespan calls `Coordinator.initialize` → `Database.migrate` → `upgrade("head")` before recovery/readiness; the image includes Alembic/migrations and Compose retains `postgres_data`. Offline SQL contains only additive DDL/version update in a transaction. The focused PostgreSQL migration regression verifies exact old match/head/token preservation except the new NULL origin, and idempotent startup upgrade. No volume reset is required; additive DDL can briefly lock the table.

Durable admission reads PostgreSQL, holds `pg_advisory_xact_lock(0x4354414E, 3)` from check through COMMIT, and uses the same session for aggregate insertion. Six independent concurrent transactions with capacity 2 accept exactly two. No peer tracking dictionary grows with socket churn. Genuine DB failure still fences writes, with no automatic switch to memory. Explicit memory budgets reset at process restart; durable budgets do not. One gameplay worker/replica remains required even though admission itself is database-serialized.

**Retention:** no automatic cleanup is added. All offline lobby reservations keep existing ownership/reconnect semantics. Active/finished matches and confirmed snapshots are never deleted or superseded by admission. Exhausted capacity refuses new creation while existing joins/Continue/start remain usable; starting an existing lobby releases its concurrent lobby capacity but not its recent creation record. Existing deployments already above the configured cap retain all data and refuse additional rooms. Raising a cap is an operator decision, not a data cleanup.

**Confirmed product limitation — final lifecycle verification, 2026-10-12:** legitimate repeated create → leave without Start Match can permanently exhaust the default 20 origin / 1000 global lobby reservations. Neither the 600-second window, guest-token expiration, elapsed `rooms.expires_at`, nor restart changes a stored `status="lobby"`; all such rows still count. A room with elapsed `expires_at` is excluded from recovery, but not from admission counts. Disconnected guests with valid credentials and offline account seats remain reconnectable and must not be treated as abandoned.

The existing internal [close_room](../../app/server_mp.py) commits explicit `closed` status and credential revocation before removing the RAM entry; closing a verified never-started lobby frees both lobby quotas while retaining all durable rows. A committed non-lobby state such as `expired` also falls outside the count predicate, but no automatic expiry writer, public Close action or administrative closure command exists. `RoomManager.destroy_room` alone only removes RAM and cannot reclaim durable capacity. **Do not use `close_room` as an automatic sweep:** it can mark an active match abandoned if invoked on one. Successful Start Match is the only ordinary user lifecycle transition that releases a lobby reservation. Safe explicit retirement tooling/policy remains deferred.

Final focused checks: **36 passed** across local admission and PostgreSQL tests, including four new cases: IP/global capacity released by explicit never-started closure with rows retained across restart, and capacity retained after credential/room timestamp expiry across restart. Existing tests cover reconnectable offline retention, window expiry, Start Match release and protected match/rematch history. These checks supplement the earlier full 1342-test run; no new full-suite result is claimed.

**Deferred expiry policy:** prove under room/database locks that a room never started (`match_no=0`, no current or historical Match), has no recoverable account membership or valid guest credential, and meets an approved inactivity policy. Only then could a maintenance operation COMMIT an explicit expired state. The existing disconnect/leave path retains named members and cannot establish these conditions; account ownership has no implicit offline expiry. TTL/maintenance operations and closed-data retention need a separate lifecycle task. A global cap bounds simultaneous unstarted lobby growth, not every legitimate match/history byte or a distributed denial of service; address rotation can exhaust the shared cap.

Focused tests — [test_room_creation_limits.py](../../tests/test_room_creation_limits.py), [test_room_creation_postgres.py](../../tests/test_room_creation_postgres.py). Real bounded Docker/Nginx/PG raw WebSocket acceptance — [test_room_creation_docker.py](../../tests/test_room_creation_docker.py). Add [room_limits.compose.yaml](../../tests/room_limits.compose.yaml) after the SEC-04 overlay under a **separate disposable** project, with strict 3/window, 5/IP lobby and 100 global limits; fresh actual IPv6 probe addresses permit repeats without clearing durable budgets. Backend remains IPv4 internally; Nginx accepts IPv6 and supplies that real client to trusted Uvicorn. Test-only full-suite fixtures use larger finite limits because hundreds of unrelated test rooms share one disposable DB; SEC-03 tests explicitly restore small budgets and verify production defaults.

```powershell
docker compose --env-file .env.example -p catan-sec03-test -f compose.yaml -f tests/auth_proxy.compose.yaml -f tests/room_limits.compose.yaml up --build -d --wait
$env:CATAN_ROOM_LIMIT_TEST_PROJECT = 'catan-sec03-test'
python -B -m pytest tests/test_room_creation_docker.py -p no:cacheprovider
docker compose --env-file .env.example -p catan-sec03-test -f compose.yaml -f tests/auth_proxy.compose.yaml -f tests/room_limits.compose.yaml stop
```

All test ports bind localhost, separate networks/volumes/databases preserve the user's PostgreSQL data. Full verification status and remaining limits — [[Project State]], [[Результаты аудита#SEC-03 room creation quotas — verified 2026-10-12]].

Verified: Docker backend/web build, host/container pip check, nginx -t, previous-schema upgrade and real Chrome/Nginx/PG cross-browser/mixed-room/claim/logout/SIGKILL/full down/up without -v. Test-only tests/persistence.compose.yaml explicitly sets development + origin :18081; main compose retains secure defaults. Reproduction: node web/e2e/auth.cjs using external Playwright/Chrome and the isolated catan-persistence-test project. Existing volume was retained; no normal production stack restart. Detailed gate/measurements — [[plans/persistence-auth#Auth Phase 1 — completed 2026-10-07]].

## Continue API — Persistence 1C

Verified **2026-10-06**: Docker backend/web builds, nginx -t, pip check and **10 Chrome E2E
checks** against real Nginx/PostgreSQL. [nginx.conf](../../deploy/nginx.conf) adds `/api/`
proxy to FastAPI with 16k body limit/3s connect/10s read timeout. Existing exact `/ws`,
`/health` and SPA/static routing remain. API secrets are POST bodies, never query strings;
access logs include path/status, not body. Endpoint returns no-store and safe metadata only.
Limits/privacy — [[Сервер и протокол#Recent game inspection — Persistence 1C]].

Vite dev `/api` proxy derives HTTP(S) origin from VITE_WS_URL (web/.env or process env),
otherwise 127.0.0.1:8000. Production uses site's same origin. Recent validation does not
send known manual-WS-server proofs to a different backend; legacy without origin assumes
default. No new services, port exposure, dependencies, DB migration, worker or auth cookies.

Repeat smoke after isolated build/up, using installed external Playwright/Chrome:
`node web/e2e/continue-games.cjs` with NODE_PATH pointing at that test install.
Default project `catan-persistence-test`, browser origin :18081; test-only DB port :15432
from tests/persistence.compose.yaml. Runner performs SIGKILL, down/up WITHOUT -v,
and stops backend temporarily to exercise existing internal durable close through a
one-off backend process. Never point this runner at the normal production stack.
Full pytest 535, web 147, TS/build pass; latency single 8.2ms/batch5 8.4ms local medians.
Auth/TLS/backup/multi-worker remain future. Details — [[plans/persistence-auth#Persistence Phase 1C — completed 2026-10-06]].

## Local development

Normal Vite dev now binds **127.0.0.1:5173**; normal preview binds **127.0.0.1:4173**. Network/LAN exposure requires an explicit operator override. Details and verified scope — [[Deployment#Vite development security — SEC-02]].

Из корня репозитория, желательно в своём Python 3.12 virtualenv:

```sh
python -m pip install -r requirements-server.txt
python -m app.server_mp
```

В другом терминале:

```sh
cd web
npm ci
npm run dev
```

Открыть http://127.0.0.1:5173. Backend по умолчанию слушает 0.0.0.0:8000; main() поддерживает CATAN_HOST/CATAN_PORT. Vite proxy использует VITE_WS_URL из web/.env / web/.env.local либо ws://127.0.0.1:8000/ws. Browser default — page-origin `/ws`; явный VITE_WS_URL также переопределяет browser connection, как и раньше. LAN backend URL сам по себе не открывает Vite наружу; пример override — [web/.env.example](../../web/.env.example).

Desktop по-прежнему использует свои requirements и RUN_*.bat. requirements-server.txt не устанавливает PySide или тесты. Существующий [tools/run_lan.ps1](../../tools/run_lan.ps1) остаётся способом локального запуска.

Без DATABASE_URL local dev использует memory mode; явный CATAN_PERSISTENCE_MODE=memory не допускает игнорировать заданный DB URL. Durable mode требует postgresql+psycopg URL либо полный POSTGRES_USER/PASSWORD/DB + CATAN_DATABASE_HOST. При DB outage durable mode не переключается в RAM. `python -m app.server_mp` на Windows явно использует SelectorEventLoop для psycopg; прямой Uvicorn CLI с durable DB требует `--loop app.persistence.db:selector_event_loop`. Linux Docker CMD не меняется. Основание — [Psycopg async/Windows](https://www.psycopg.org/psycopg3/docs/advanced/async.html).

## Vite development security — SEC-02

**Implemented/tested 2026-10-12.** Vite **5.4.21 → 6.4.4**, exact package pin and reproducible `npm ci`. [Official release policy](https://vite.dev/releases) currently supports 6.4 for security backports. Node 24.12.0 and existing `@vitejs/plugin-react` 4.7.0 satisfy engines/peers; React, TypeScript and the plugin are not upgraded. Only Vite and its necessary esbuild/globbing dependency subtree changed in the lockfile. No audit-force update, Docker image/architecture or Nginx configuration change.

Advisory applicability checked against primary sources:

- [GHSA-fx2h-pf6j-xcff](https://github.com/vitejs/vite/security/advisories/GHSA-fx2h-pf6j-xcff): Windows ADS/8.3 deny bypass, patched in 6.4.3 and included in 6.4.4.
- **October 6, 2026:** [GHSA-rq7h-c2jc-7f22](https://github.com/vitejs/vite/security/advisories/GHSA-rq7h-c2jc-7f22) (non-Windows safe-module allow bypass) and [GHSA-9jrq-w75r-8gcw](https://github.com/vitejs/vite/security/advisories/GHSA-9jrq-w75r-8gcw) (custom-middleware cross-origin script) are patched in 6.4.4. CATAN uses normal SPA mode, not the affected custom HTML middleware.
- [GHSA-vfpm-58rq-9qcg](https://github.com/vitejs/vite/security/advisories/GHSA-vfpm-58rq-9qcg), also October 6, affects 8.2/8.3; neither old Vite 5 nor selected 6.4 is in its affected range. Do not describe it as a Vite 6 vulnerability fixed by this update.

Dev/preview defaults are **127.0.0.1**. Synthetic Windows reproduction on 5.4.21 returned direct `.env` 403 but `::$DATA?raw` 200 with the canary. After upgrade, stock exact deny patterns still missed resolved raw-query suffixes locally; explicit `.env*`/`*.{crt,pem}*` patterns close this tested gap and retain `.git` denial. Resolving direct/raw/ADS requests now return refusal without file contents; percent-encoded paths that do not resolve return the normal HTML SPA fallback, also without the canary. Strict allow-list and patched path checks are not disabled. Real secrets/private files were never requested. Native 8.3 filename generation and the Linux/custom-middleware exploit chains were not separately reproduced; their upstream fixes are included by version, not claimed as local exploit acceptance.

Verified: six [live Vite security groups](../../web/tests/viteSecurity.test.mjs), all **275 web tests**, TypeScript, production build, `docker compose build web` with existing Node 24 Alpine/Nginx and actual Windows listener addresses. Real Chrome/two guests/isolated PostgreSQL also passed Home/create/join/Base start, `/api/auth/me`, same-origin `/ws`, personalized privacy and visible Board3D/terrain GLBs, no JS errors. Backend test used localhost 18092 because Windows reserves 7929–8028; Vite proxy was temporarily overridden for the probe and guest Advanced connection pointed to Vite `/ws`. Repository defaults remain backend 8000. Temporary services are stopped after verification; existing development/production DBs, accounts and volumes are untouched.

At SEC-02 verification, `npm audit` reported **17 affected dev-toolchain package records: 15 high, 1 moderate, 1 low; 0 critical**. `npm audit --omit=dev`: **0**. Remaining chains include Rollup, PostCSS/nanoid/source-map-js, Babel/browserslist/baseline-browser-mapping and ESLint/glob tools. They are not additional Vite GHSA records and are not fixed in this scope; build-time risks remain. Large Board3D chunk warning remains. Python/scenario suites were not repeated for SEC-02 because backend/gameplay were unchanged; SEC-01's full 1292 result is separate evidence. SEC-03/04 were not started at that checkpoint; SEC-04's later state is described above. [[Project State]], [[Результаты аудита#SEC-02 Vite hardening — verified 2026-10-12]].

## Docker production-like

Из корня, при работающем Docker Engine / Docker Desktop в Linux containers mode:

```sh
docker compose up --build
```

Открыть **http://localhost**. Для второго устройства в той же сети — http://<LAN-IP host>, если доступ разрешён сетевыми настройками host. WebSocket URL вводить вручную не требуется.

Compose всегда задаёт durable mode. [.env.example](../../.env.example) содержит local-only DB defaults; реальный root .env ignored и исключён из build context. POSTGRES_DB/USER/PASSWORD передаются Postgres и backend через env; URL.create безопасно обрабатывает символы пароля. Optional DATABASE_URL имеет приоритет и должен использовать percent-encoded password. Ничего из credentials не попадает в frontend bundle.

Backend ждёт healthy PostgreSQL, выполняет Alembic upgrade head, затем validates/loads recoverable Room checkpoints. Web ждёт readiness backend. Повторный up не сбрасывает schema/state. Не запускать второй backend worker/replica или migration от каждого запроса. RAM rooms старого running image не импортируются автоматически; controlled drain/upgrade — отдельный rollout.

Запуск в фоне с проверкой готовности:

```sh
docker compose up --build -d --wait
docker compose ps
docker compose logs -f
```

Завершение:

```sh
docker compose down
```

`postgres_data` named volume сохраняется при down и backend/PostgreSQL restart. `down -v` удаляет durable данные; это отдельное явное destructive действие, не штатный restart/обновление. Volume не заменяет backup. Политика восстановления — [[Сервер и протокол#Durable command and recovery flow — Persistence 1B]].

Если порт 80 занят, задать CATAN_WEB_PORT, например в PowerShell:

```powershell
$env:CATAN_WEB_PORT = "8080"
docker compose up --build
```

Тогда адрес — http://localhost:8080, WebSocket — ws://localhost:8080/ws. Это настройка host port Compose, не переменная browser bundle.

## Ports and architecture

```mermaid
flowchart LR
    B[Browser] -->|HTTP host :80| N[Nginx web container :8080]
    N -->|"/ → static React dist"| F[Production assets]
    N -->|"/ws → WS upgrade"| A[FastAPI backend :8000]
    N -->|"/health → HTTP"| A
    A --> E[Shared Python engine]
    A --> R[RoomManager in memory]
    A -->|"SQLAlchemy async / committed heads"| P[PostgreSQL :5432 private]
    P --> V[postgres_data named volume]
```

| Service / route | Поведение |
| --- | --- |
| web | Единственный опубликованный host port: 80, override CATAN_WEB_PORT |
| backend | Private 8000 в proxy/default networks; ports mapping отсутствует, trusted proxy peer — только web |
| postgres | Private 5432 в default network с backend, web не подключён; без host ports; named volume, pg_isready healthcheck |
| / | React production build, SPA fallback на index.html |
| /assets/ | Реальные static files; отсутствующий asset возвращает 404 |
| /ws | Только exact route; HTTP/1.1, Upgrade/Connection headers, 3600s proxy read/send timeout |
| /health | 200 {status:ok,ready:true,persistence:postgresql}; DB/schema/recovery unavailable → 503/ready:false |

Frontend не использует другие backend HTTP API. Автоматические FastAPI /docs /redoc /openapi.json наружу через Nginx не проксируются. Nginx использует Docker DNS для backend, внешний hostname не задан.

backend healthcheck обращается к 127.0.0.1:8000/health через Python stdlib. web зависит от service_healthy, а не только от факта создания контейнера. Readiness включает DB/schema/recovery, не создаёт комнат и не выполняет gameplay. DB monitor проверяет доступность и разрешает fenced writes через committed head, не через повторное выполнение.

## WebSocket configuration

[wsClient.ts](../../web/src/wsClient.ts) экспортирует defaultWebSocketUrl(), который используют App и fallback WSClient.connect:

- Production build: protocol страницы http/https → ws/wss, host и port берутся из window.location, путь /ws.
- Development: VITE_WS_URL либо локальный backend 127.0.0.1:8000.
- Production намеренно не использует локальный VITE_WS_URL. В собранном Docker bundle подтверждено отсутствие hardcoded localhost/LAN backend addresses.
- .env/.env.local не попадают в Docker build context. UI field URL остаётся существующим ручным override; layout не менялся.

TLS в Compose не добавлен; HTTPS deployment и trust forwarded headers за внешним proxy — отдельная задача.

## Images and dependencies

| Файл | Назначение |
| --- | --- |
| [compose.yaml](../../compose.yaml) | Три сервиса, private DB/volume, web host port, readiness и stop grace period |
| [backend.Dockerfile](../../deploy/backend.Dockerfile) | Official Python 3.12 slim-bookworm, non-root uid 10001, один Uvicorn worker |
| [web.Dockerfile](../../deploy/web.Dockerfile) | Official Node 24 Alpine → npm ci/build → official Nginx Alpine, non-root nginx uid 101 |
| [nginx.conf](../../deploy/nginx.conf) | Static/SPA, /api/, /ws и /health proxy; pid в /tmp |
| [.dockerignore](../../.dockerignore) | Allowlist необходимых исходников/config/maps; excludes env, credentials, docs/tests, caches, node_modules и desktop/legacy |
| [requirements-server.txt](../../requirements-server.txt) | Точно закреплённые server + SQLAlchemy/Alembic/psycopg/support dependencies, отдельные от desktop/tests |
| [package-lock.json](../../web/package-lock.json) | npm ci input; дополнены пропущенные зависимости, уже объявленные package.json |

Base images, включая PostgreSQL 17-bookworm, закреплены OCI digest; обновляются осознанно. Backend копирует server/protocol/room_options/game_events/test_tools, engine/maps, persistence codec/DB adapter и Alembic/migrations. PySide, pytest, desktop SVG и Node не нужны backend runtime. В web runtime нет Node/node_modules/исходников, только Nginx и dist.

Проверенные 2026-10-06 image inspect Size: **backend 65.4 MB, web 26.4 MB**. Node build stage не входит в финальный web image. Исторический docker image ls из Infrastructure Phase 1 сообщал 215/93 MB; это другая метрика Docker Desktop, не размер скачивания по сети.

Исходный package-lock не соответствовал package.json: npm ci в чистом image находил отсутствующие ESLint/TypeScript ESLint dependencies. Lockfile синхронизирован; добавлены 251 package entries, версии всех ранее зафиксированных пакетов сохранены. package.json и framework/tooling не менялись.

## Worker count and shutdown

Запуск backend: python -m uvicorn app.server_mp:app --host 0.0.0.0 --port 8000 --workers 1 --timeout-graceful-shutdown 10. Exec-form CMD доставляет сигнал самому процессу. reload/debug отсутствуют; не используется gunicorn.

**Только один worker и одна backend replica.** Каждый процесс иначе получил бы собственные RoomManager, комнаты и GameState, и клиенты одной комнаты могли бы оказаться в разных состояниях. Docker не меняет эту архитектуру.

Nginx также запускается exec-form как non-root, STOPSIGNAL SIGQUIT. worker_shutdown_timeout=10s ограничивает ожидание живых WebSocket; Compose stop_grace_period=20s у обоих сервисов. При остановке активное WS может закрыться без WebSocket close frame, что клиент обрабатывает существующим reconnect flow.

## Persistence integration tests

Изолированный stack — [tests/persistence.compose.yaml](../../tests/persistence.compose.yaml), project `catan-persistence-test`, web 127.0.0.1:18081 и тестовый DB port 127.0.0.1:15432. Production compose PostgreSQL port не публикует. Не использовать production room/volume для failure/deletion tests.

```powershell
docker compose -p catan-persistence-test -f compose.yaml -f tests/persistence.compose.yaml up --build -d --wait
docker compose -p catan-persistence-test -f compose.yaml -f tests/persistence.compose.yaml exec postgres psql -U catan -d catan -c "CREATE DATABASE catan_persistence_test;"
$env:CATAN_TEST_DATABASE_URL = 'postgresql+psycopg://catan:catan-local-only@127.0.0.1:15432/catan_persistence_test'
python -B -m pytest -p no:cacheprovider
```

CREATE DATABASE нужен один раз для свежего test volume. [test_persistence_postgres.py](../../tests/test_persistence_postgres.py) требует явный *_test URL, без него DB cases skipped; иные DB names rejected. Только в disposable test DB migration case делает downgrade/reupgrade. Обычный Docker backend использует catan, не эту pytest DB.

[persistence-restart.cjs](../../web/e2e/persistence-restart.cjs) запускается из repo root с внешним Playwright + installed Chrome; NODE_PATH указывает на его node_modules. `node web/e2e/persistence-restart.cjs` проверяет ordinary UI + isolated Docker restarts и down без -v; reports/screenshots идут в TEMP, без raw persistence payload. Удаление volume доступно только отдельным explicit CATAN_PERSISTENCE_DELETE_TEST_VOLUME=1: runner проверяет exact volume name и Compose project label. Default suite не удаляет volume. Это не команда для normal production stack.

## Persistence verification — 2026-10-06

- Full pytest **508 passed**, включая 63 cases с real PostgreSQL JSONB/FK/locking, reversible Alembic migration, full private state/lifecycle/rollback/corruption, lost ACK/ambiguous COMMIT, stable/revoked credentials и killed separate backend process/real WS.
- Web **130 passed**, TypeScript, production web build, Docker backend/web build и local/image pip check. Existing Dice prepared Chrome flow — 5 accepted commands, no JS errors. Engine/rules/maps/codec/renderers untouched; scenarios not rerun, 348/508 remains historical.
- Chrome **154.0.8037.98**, два обычных клиента через actual Nginx/FastAPI/PostgreSQL: Base Standard, Balanced/Hidden/60s/white-orange, natural setup/Roll/resource-funded paid road/chat/refresh; backend SIGKILL then action and second restart. Board/turn/own hands/VP/dice/chat/settings/colors and private state/deck/bag/seq digests stable; Hidden bank/foreign hands remain protected. Recovered board screenshot inspected.
- PostgreSQL stop/start without volume deletion: no premature success/tick, retryable failure, pending Roll commits exactly once after DB returns. Full Compose down/up without -v restores same match; separately inspected isolated down -v/up yields 0 rooms. Normal running production stack/data not modified.
- Startup with unavailable DB: readiness 503, retryable persistence_unavailable and WS 1013; no memory fallback. Current-head corruption quarantines only affected room and never rolls back to older ACKed snapshot.
- Median durable command overhead about 22–23ms, encode 2.10–2.35ms + SQL 19.68–20.50ms; 12 warm local samples/command. Detailed method/limits — [[plans/persistence-auth#Verification and performance — 2026-10-06]]. No production load/TLS/backup/ARM certification.

## Historical infrastructure verification — 2026-10-04

- docker compose build и up -d --wait завершились успешно; backend healthy перед стартом web.
- Реальный headless Chrome, два независимых browser contexts: HTML/CSS/JS загружены через Nginx, WS у обоих ws://localhost/ws, Host → Join → Start Match, 19 тайлов у обоих клиентов.
- Через React UI выполнены все 8 setup placements и Roll: 9 ACK applied=true, tick=9 у обоих, одинаковые публичные постройки/roll; чужие res и seed отсутствуют. Browser page errors отсутствуют. Изображение поля просмотрено.
- /health возвращает 200/status ok; missing static asset → 404, SPA fallback → 200.
- Проверены non-root users, отсутствие host mounts и backend port publishing, наличие 12 maps, отсутствие PySide/pytest в backend image; pip check и nginx -t успешны.
- docker compose down удаляет оба контейнера и сеть; оба процесса завершаются с exit code 0. Также проверено завершение с живым WS: около 11 секунд, внутри заданного grace period.
- pytest: **158 passed**, без skip; команда python -B -m pytest -q -o addopts= -p no:cacheprovider. addopts переопределены, поскольку в текущем окружении нет pytest-cov из setup.cfg; тесты не исключались.
- Web: **25 passed** (21 прежний + 4 URL behavior cases); npm run type-check и npm run build успешны после чистого npm ci. URL tests покрывают HTTP origin/port, HTTPS→wss и оба dev defaults.
- Gameplay engine не менялся; scenario suite не повторялась. Последний исторический baseline: 348/508.

## Known limitations

- Local memory mode всё ещё теряет rooms при restart; durable Compose восстанавливает committed state. Older RAM-only running games не появляются в DB автоматически.
- Нет горизонтального масштабирования, TLS, accounts/auth или публичного production security review. Inspection имеет собственный bounded single-worker rate limit; остальные endpoints не получили общий rate-limiting framework.
- Один backend worker/replica; нет accounts, automatic retention scheduler или backup system. Hash-only guest tokens не восстанавливаются по имени при потере browser proof.
- Проверен Linux/amd64 Docker Desktop и локальные browser contexts/Windows backend process. Полная естественная партия, нагрузка, ARM и отдельные LAN-устройства не проверялись.
- npm audit сообщал 18 advisories в dev/build dependency tree; npm audit --omit=dev показал 0. Они не устранялись обновлением tooling в рамках контейнеризации; Node build dependencies не входят в Nginx runtime image.

Официальные основания конфигурации: [Nginx WebSocket proxy](https://nginx.org/en/docs/http/websocket.html), [Compose startup/readiness](https://docs.docker.com/compose/how-tos/startup-order/).
