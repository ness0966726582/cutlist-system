#!/bin/sh
# NAS 更新：sh update.sh [版本]   例：sh update.sh 1.0.1   不給版本 = latest
# 先備份，再拉新映像重啟。
set -e
cd "$(dirname "$0")"
sh ./backup.sh
if [ -n "$1" ]; then
  grep -q '^CUTLIST_VERSION=' .env && sed -i "s/^CUTLIST_VERSION=.*/CUTLIST_VERSION=$1/" .env || echo "CUTLIST_VERSION=$1" >> .env
fi
docker compose pull
docker compose up -d
sleep 5
echo "更新完成，版本：$(docker exec cutlist-api cat /app/VERSION 2>/dev/null || echo ?)  請操作者按 Ctrl+F5。"
docker compose ps
