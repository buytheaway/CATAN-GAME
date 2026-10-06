---
tags: [catan, deployment, docker]
updated: 2026-10-06
---

# Deployment

[[Project State]] · [[Точки входа]] · [[Сервер и протокол]] · [[Architecture Decisions]] · [[plans/containerization]]

Production Infrastructure Phase 1 добавила Docker Compose; Persistence 1B добавляет durable PostgreSQL и startup recovery. Проверено 2026-10-06 на Docker Desktop Linux containers, Windows host. Это production-like запуск с persistence, без TLS/accounts, не готовый публичный internet deployment.

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

Открыть http://localhost:5173. Backend по умолчанию слушает 0.0.0.0:8000; main() поддерживает CATAN_HOST/CATAN_PORT. Vite dev использует VITE_WS_URL из web/.env / web/.env.local либо ws://127.0.0.1:8000/ws. Для LAN значение может быть ws://<IP backend>:8000/ws; пример — [web/.env.example](../../web/.env.example).

Desktop по-прежнему использует свои requirements и RUN_*.bat. requirements-server.txt не устанавливает PySide или тесты. Существующий [tools/run_lan.ps1](../../tools/run_lan.ps1) остаётся способом локального запуска.

Без DATABASE_URL local dev использует memory mode; явный CATAN_PERSISTENCE_MODE=memory не допускает игнорировать заданный DB URL. Durable mode требует postgresql+psycopg URL либо полный POSTGRES_USER/PASSWORD/DB + CATAN_DATABASE_HOST. При DB outage durable mode не переключается в RAM. `python -m app.server_mp` на Windows явно использует SelectorEventLoop для psycopg; прямой Uvicorn CLI с durable DB требует `--loop app.persistence.db:selector_event_loop`. Linux Docker CMD не меняется. Основание — [Psycopg async/Windows](https://www.psycopg.org/psycopg3/docs/advanced/async.html).

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
| backend | Порт 8000 доступен внутри Compose network; ports mapping отсутствует |
| postgres | Private 5432 в Compose network, без host ports; named volume, pg_isready healthcheck |
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
