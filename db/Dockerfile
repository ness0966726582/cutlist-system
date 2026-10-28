FROM postgres:16-alpine
# 初始化 SQL 打包進映像檔 (第一次建立資料 volume 時自動執行)
COPY init/ /docker-entrypoint-initdb.d/
