#!/bin/bash
# First-boot setup of the API server (runs once, as root).
# Installs Docker + Compose and adds swap. The application itself is put
# here and started by the CI/CD pipeline (deploy/aws/deploy.sh).
set -euxo pipefail

# The Elastic IP is attached a few seconds after boot: wait for internet.
for _ in $(seq 1 60); do
  curl -fsS -m 5 https://cdn.amazonlinux.com > /dev/null 2>&1 && break
  sleep 5
done

# 2 GB of swap: the free-tier instance has 1 GB of RAM, and LaTeX/PDF jobs
# need short bursts of extra memory.
if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

dnf install -y docker
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL -o /usr/local/lib/docker/cli-plugins/docker-compose \
  https://github.com/docker/compose/releases/download/v5.6.1/docker-compose-linux-x86_64
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
systemctl enable --now docker

mkdir -p /opt/docling
chmod 700 /opt/docling
