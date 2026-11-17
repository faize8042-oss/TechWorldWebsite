#!/bin/sh
# Fresh Ubuntu 24.04 amd64 host. Installs tools, never opens SSH/firewall rules.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run as root.' >&2; exit 1; }
. /etc/os-release
[ "$ID" = ubuntu ] && [ "$VERSION_ID" = 24.04 ] && [ "$(dpkg --print-architecture)" = amd64 ] || {
  echo 'Supported host: Ubuntu 24.04 amd64.' >&2; exit 1;
}
apt-get update
apt-get install -y ca-certificates curl git python3 age certbot
install -m 0755 -d /etc/apt/keyrings
curl --fail --silent --show-error --location https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<'EOF'
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker compose version
echo 'Host tools ready. Configure DNS and provider firewall before certificate issuance.'
