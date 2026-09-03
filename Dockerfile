FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    bash \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --home-dir /home/codex --shell /bin/bash codex

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY cli ./cli

RUN mkdir -p /workspaces /data /home/codex/.codex \
    && chown -R codex:codex /app /workspaces /data /home/codex

USER codex

ENV PYTHONUNBUFFERED=1 \
    HOME=/home/codex \
    CODEX_HOME=/home/codex/.codex

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
