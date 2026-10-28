#!/usr/bin/env bash
# Linux / NAS (Synology, Ubuntu…) 第一次啟動：bash scripts/install.sh [web_port] [db_port]
set -e
cd "$(dirname "$0")/.."
WEB_PORT="${1:-8100}"; DB_PORT="${2:-15434}"
command -v docker >/dev/null || { echo "請先安裝 Docker (https://docs.docker.com/engine/install/)"; exit 1; }
if [ ! -f .env ]; then
  PW=$(tr -dc 'a-z0-9' </dev/urandom | head -c 16)
  printf 'POSTGRES_PASSWORD=%s\nWEB_PORT=%s\nDB_PORT=%s\n' "$PW" "$WEB_PORT" "$DB_PORT" > .env
  echo "已建立 .env（資料庫密碼隨機產生）"
fi
docker compose up -d --build
echo "啟動完成：http://$(hostname -I 2>/dev/null | awk '{print $1}'):$WEB_PORT"
