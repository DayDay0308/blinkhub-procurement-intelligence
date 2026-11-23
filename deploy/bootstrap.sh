#!/usr/bin/env bash
# First-boot setup for the BlinkHub demo server (Ubuntu 24.04). Safe to run again.
# Called by the EC2 user data (infra/terraform) with these variables set:
#   REPO_URL, BRANCH, DOMAIN, DOCUMENT_BUCKET, AWS_REGION
set -euo pipefail
exec > >(tee -a /var/log/blinkhub-bootstrap.log) 2>&1
echo "== BlinkHub bootstrap $(date -Is)"

APP=/opt/blinkhub

# 1. Swap: the t3.small has 2 GB RAM; building the images needs a bit more headroom.
if ! swapon --show | grep -q /swapfile; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# 2. Docker (Ubuntu packages) and the AWS CLI (to read the optional AI key).
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q docker.io docker-compose-v2 git openssl
systemctl enable --now docker
command -v aws >/dev/null || snap install aws-cli --classic

# 3. Code
if [ ! -d "$APP/.git" ]; then
  git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$APP"
fi
cd "$APP"

# 4. Secrets: generated here, once, and never leave the server.
if [ ! -f .env ]; then
  umask 077
  cat > .env <<ENV
ENVIRONMENT=production
DOMAIN=$DOMAIN
AWS_REGION=$AWS_REGION
DOCUMENT_BUCKET=$DOCUMENT_BUCKET
POSTGRES_USER=blinkhub
POSTGRES_PASSWORD=$(openssl rand -hex 24)
JWT_SECRET=$(openssl rand -hex 32)
DATA_ENCRYPTION_KEY=$(openssl rand -hex 32)
ASK_DB_PASSWORD=$(openssl rand -hex 24)
SEED_ON_START=true
SEED_SYNTHETIC=true
DEMO_PASSWORD=Demo@2026!
ENV
fi

# 5. Optional AI key from SSM Parameter Store (SecureString), if you created one.
KEY=$(aws ssm get-parameter --region "$AWS_REGION" --name /blinkhub/anthropic_api_key \
      --with-decryption --query Parameter.Value --output text 2>/dev/null || true)
if [ -n "$KEY" ] && ! grep -q '^ANTHROPIC_API_KEY=.' .env; then
  sed -i '/^ANTHROPIC_API_KEY=/d' .env && echo "ANTHROPIC_API_KEY=$KEY" >> .env
fi

# 6. Start
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
echo "== Done. Open https://$DOMAIN"
