#!/usr/bin/env bash
# Linux / NAS 更新：bash scripts/update.sh [tag]
set -e
cd "$(dirname "$0")/.."
bash scripts/backup.sh
git fetch --tags origin
if [ -n "$1" ]; then git checkout -q "$1"; else git checkout -q main && git pull --ff-only origin main; fi
docker compose up -d --build
echo "更新完成，版本 v$(cat VERSION)。請操作者按 Ctrl+F5。"
