FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY html /usr/share/nginx/html
# 每次 build 把 index.html 的 __BUILD__ 換成時間戳，瀏覽器就不會沿用舊的 app.js / style.css
RUN sed -i "s/__BUILD__/$(date +%Y%m%d%H%M%S)/g" /usr/share/nginx/html/index.html
