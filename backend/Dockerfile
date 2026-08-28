FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DATABASE_URL=sqlite:///./data/traffic.db
EXPOSE 8000

# Platforms like Railway inject a dynamic $PORT and route to it; fall back to
# 8000 for plain `docker run`/docker-compose where no PORT is set.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
