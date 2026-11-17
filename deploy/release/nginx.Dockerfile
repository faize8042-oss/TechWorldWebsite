FROM nginx:stable-alpine@sha256:901e593c95dc85f5a729f5765516321366ef4ac401821431d408897e95287d0a
RUN addgroup -g 10002 proxytransport \
    && sed -i 's/^user .*;/user nginx proxytransport;/' /etc/nginx/nginx.conf \
    && sed -i 's@^pid .*;@pid /run/nginx/nginx.pid;@' /etc/nginx/nginx.conf
