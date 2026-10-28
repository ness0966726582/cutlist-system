#!/usr/bin/env bash
# Linux / NAS 備份：bash scripts/backup.sh  → backups/<時間>/db.dump + files.tgz（保留 30 份）
set -e
cd "$(dirname "$0")/.."
DIR="backups/$(date +%Y%m%d_%H%M%S)"; mkdir -p "$DIR"
docker exec cutlist-db pg_dump -U cutlist -d cutlist -F c > "$DIR/db.dump"
docker run --rm -v cutlist-system_cutlist_files:/data -v "$(pwd)/$DIR:/backup" alpine tar czf /backup/files.tgz -C /data .
cp .env "$DIR/.env" 2>/dev/null || true
echo "備份完成：$DIR"
ls -1d backups/*/ | sort -r | tail -n +31 | xargs -r rm -rf
