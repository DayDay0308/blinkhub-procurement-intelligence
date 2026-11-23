#!/usr/bin/env bash
# Pull the latest code and rebuild. Run on the server, or from GitHub Actions (deploy.yml).
set -euo pipefail
cd /opt/blinkhub
git fetch --depth 1 origin "${BRANCH:-main}"
git reset --hard FETCH_HEAD
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build --remove-orphans
docker image prune -f
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml ps
