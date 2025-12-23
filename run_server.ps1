param([int]$Port=8000)
.\.venv\Scripts\python.exe -m uvicorn app.server:app --host 0.0.0.0 --port $Port
