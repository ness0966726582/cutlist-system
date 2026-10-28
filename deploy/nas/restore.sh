#!/bin/sh
# NAS 還原（覆蓋目前資料）：sh restore.sh backups/20261028_221500
# 也可用來把 Windows 電腦 scripts/backup.ps1 做的備份搬到 NAS（db.dump + files.tgz 格式相同）。
set -e
cd "$(dirname "$0")"
FROM="$1"
[ -f "$FROM/db.dump" ] || { echo "找不到 $FROM/db.dump"; exit 1; }
if [ -t 0 ]; then   # 互動時才問；從 DSM 任務排程器跑 (sh restore.sh backups/xxx) 直接做
  printf "這會清掉目前資料庫與圖面，改成 %s 的內容。確定？(yes/no) " "$FROM"; read ans
  [ "$ans" = "yes" ] || exit 0
fi
docker compose up -d db
i=0; until docker exec cutlist-db pg_isready -h 127.0.0.1 -U cutlist -d cutlist >/dev/null 2>&1; do i=$((i+1)); [ $i -gt 120 ] && { echo "資料庫未就緒"; exit 1; }; sleep 2; done
docker cp "$FROM/db.dump" cutlist-db:/tmp/db.dump
docker exec cutlist-db sh -c 'export PGPASSWORD=$POSTGRES_PASSWORD; psql -h 127.0.0.1 -U cutlist -d postgres -c "DROP DATABASE IF EXISTS cutlist WITH (FORCE)" && psql -h 127.0.0.1 -U cutlist -d postgres -c "CREATE DATABASE cutlist" && pg_restore -h 127.0.0.1 -U cutlist -d cutlist /tmp/db.dump && rm -f /tmp/db.dump'
if [ -f "$FROM/files.tgz" ]; then
  mkdir -p data/files && rm -rf data/files/* && tar xzf "$FROM/files.tgz" -C data/files
fi
docker compose up -d
echo "還原完成。"
