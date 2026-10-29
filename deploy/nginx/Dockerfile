FROM nginx:1.28.1-alpine
# Main-context user directive: workers use the socket group without sharing UID.
RUN addgroup -g 10002 proxytransport \
    && sed -i 's/^user .*;/user nginx proxytransport;/' /etc/nginx/nginx.conf \
    && sed -i 's@^pid .*;@pid /run/nginx/nginx.pid;@' /etc/nginx/nginx.conf
