FROM nginx:alpine

# 빌드 컨텍스트는 프로젝트 루트 (docker build -f docker/admin-web/Dockerfile .)
COPY docker/admin-web/nginx.conf /etc/nginx/conf.d/default.conf
COPY src/gov_notice/web/static/ /usr/share/nginx/html/
