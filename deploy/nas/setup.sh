#!/bin/sh
# NAS 一鍵安裝 / 升級：sudo sh setup.sh
# 做的事：有 images-*.tar 就載入映像（離線，不用 GitHub 登入）→ 沒 .env 就建 → 啟動 → 資料庫是空的且有 backups/ 就自動還原 → 印出網址
set -e
cd "$(dirname "$0")"
command -v docker >/dev/null 2>&1 || { echo "找不到 docker，請先在套件中心安裝 Container Manager"; exit 1; }

# 1. 離線映像
for t in images-*.tar images-*.tar.gz; do
  [ -f "$t" ] || continue
  echo "載入映像 $t ..."
  case "$t" in *.gz) gunzip -c "$t" | docker load ;; *) docker load -i "$t" ;; esac
done

# 2. .env
if [ ! -f .env ]; then
  PW=$(head -c 48 /dev/urandom | tr -dc 'a-z0-9' | head -c 20)
  VER=$(ls images-*.tar* 2>/dev/null | head -1 | sed 's/images-\(.*\)\.tar.*/\1/')
  printf 'POSTGRES_PASSWORD=%s\nWEB_PORT=8100\nCUTLIST_VERSION=%s\n' "$PW" "${VER:-latest}" > .env
  echo "已建立 .env（資料庫密碼隨機，請勿刪除）"
fi
mkdir -p data/db data/files
# Synology 的 @eaDir 會讓 PostgreSQL 第一次初始化失敗；資料庫實際放在 data/db/pgdata (compose 的 PGDATA)
[ -d data/db/pgdata ] || rm -rf data/db/@eaDir

# 3. 啟動
docker compose up -d
echo "等待資料庫就緒..."
i=0; until docker exec cutlist-db pg_isready -U cutlist -d cutlist >/dev/null 2>&1; do i=$((i+1)); [ $i -gt 60 ] && { echo "資料庫 60 秒內未就緒"; docker compose ps; exit 1; }; sleep 2; done
sleep 3

# 4. 第一次安裝且附帶備份 → 自動還原（只在資料庫沒有任何專案時）
LATEST=$(ls -1d backups/*/ 2>/dev/null | sort | tail -1)
if [ -n "$LATEST" ] && [ -f "$LATEST/db.dump" ]; then
  N=$(docker exec cutlist-db psql -U cutlist -d cutlist -At -c "select count(*) from projects" 2>/dev/null || echo 0)
  if [ "${N:-0}" = "0" ]; then
    echo "資料庫是空的，從 $LATEST 還原..."
    docker cp "$LATEST/db.dump" cutlist-db:/tmp/db.dump
    docker exec cutlist-db sh -c "pg_restore -U cutlist -d cutlist --clean --if-exists /tmp/db.dump; rm -f /tmp/db.dump" || true
    [ -f "$LATEST/files.tgz" ] && tar xzf "$LATEST/files.tgz" -C data/files
    docker compose restart api >/dev/null
    echo "還原完成。"
  fi
fi

IP=$(ip -4 addr 2>/dev/null | grep -oE 'inet [0-9.]+' | grep -v '127.0.0.1' | head -1 | cut -d' ' -f2)
echo ""
echo "======================================================"
echo " 安裝完成：http://${IP:-NAS的IP}:$(grep '^WEB_PORT=' .env | cut -d= -f2)"
echo " 版本：$(docker exec cutlist-api cat /app/VERSION 2>/dev/null || echo ?)"
echo " 更新：sudo sh update.sh    備份：sudo sh backup.sh"
echo "======================================================"
docker compose ps
