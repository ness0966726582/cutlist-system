#!/bin/sh
# NAS 備份：sh backup.sh → backups/<時間>/db.dump + files.tgz，保留 30 份
# 可放進 DSM 控制台 → 任務排程器 每天執行。
set -e
cd "$(dirname "$0")"
DIR="backups/$(date +%Y%m%d_%H%M%S)"; mkdir -p "$DIR"
docker exec cutlist-db pg_dump -U cutlist -d cutlist -F c > "$DIR/db.dump"
tar czf "$DIR/files.tgz" -C data/files . 2>/dev/null || true
cp .env "$DIR/.env" 2>/dev/null || true
echo "備份完成：$DIR ($(du -sh "$DIR" | cut -f1))"
ls -1d backups/*/ 2>/dev/null | sort -r | tail -n +31 | xargs -r rm -rf
