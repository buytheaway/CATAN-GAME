FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt \
    && useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin catan

COPY app/__init__.py app/server_mp.py app/net_protocol.py app/resource_path.py app/room_options.py ./app/
COPY app/engine/ ./app/engine/
COPY app/assets/maps/ ./app/assets/maps/

USER catan
EXPOSE 8000

# RoomManager is process-local: exactly one worker, even if WEB_CONCURRENCY is set.
CMD ["python", "-m", "uvicorn", "app.server_mp:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "10"]
