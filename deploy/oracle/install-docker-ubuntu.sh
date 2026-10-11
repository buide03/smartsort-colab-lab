#!/usr/bin/env bash
# For a NEW Ubuntu 24.04 VM. Uses Docker's official apt repository.
set -euo pipefail
if [[ "${EUID}" -ne 0 ]]; then
  echo 'Run with sudo bash deploy/oracle/install-docker-ubuntu.sh' >&2
  exit 1
fi
. /etc/os-release
if [[ "$ID" != ubuntu || "$VERSION_ID" != 24.04 ]]; then
  echo 'This installer targets Ubuntu 24.04. Use the Docker official guide for other systems.' >&2
  exit 1
fi
if docker compose version >/dev/null 2>&1; then
  echo 'Docker Compose is already installed.'
  exit 0
fi
apt-get update
apt-get install -y ca-certificates curl git python3
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
architecture="$(dpkg --print-architecture)"
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' \
  "$architecture" "$VERSION_CODENAME" > /etc/apt/sources.list.d/smartsort-docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker compose version
