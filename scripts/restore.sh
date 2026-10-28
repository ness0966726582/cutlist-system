#!/usr/bin/env bash
# Linux 原始碼部署的還原（覆蓋目前資料）：bash scripts/restore.sh backups/20261028_221500
set -e
cd "$(dirname "$0")/.."
FROM="$1"
[ -f "$FROM/db.dump" ] || { echo "找不到 $FROM/db.dump"; exit 1; }
read -r -p "這會清掉目前資料庫與圖面，改成 $FROM 的內容。確定？(yes/no) " ans
[ "$ans" = "yes" ] || exit 0
docker compose up -d db
sleep 5
docker cp "$FROM/db.dump" cutlist-db:/tmp/db.dump
docker exec cutlist-db sh -c "psql -U cutlist -d postgres -c 'DROP DATABASE IF EXISTS cutlist WITH (FORCE)' && psql -U cutlist -d postgres -c 'CREATE DATABASE cutlist' && pg_restore -U cutlist -d cutlist /tmp/db.dump && rm -f /tmp/db.dump"
if [ -f "$FROM/files.tgz" ]; then
  docker run --rm -v cutlist-system_cutlist_files:/data -v "$(cd "$FROM" && pwd):/backup" alpine sh -c "rm -rf /data/* && tar xzf /backup/files.tgz -C /data"
fi
docker compose up -d
echo "還原完成。"
