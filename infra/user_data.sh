#!/bin/bash
# =============================================================================
# DoSomething-scraper EC2 Bootstrap Script
# This is a Terraform templatefile — variables are injected by Terraform
# at plan/apply time before being sent to EC2 as user_data.
#
# This script runs ONCE on first EC2 boot.
# Logs: /var/log/dosomething-scraper-init.log
# =============================================================================
set -eux
exec > >(tee /var/log/dosomething-scraper-init.log) 2>&1

echo "=== DoSomething-scraper Bootstrap: $(date) ==="

# ── 1. System packages ─────────────────────────────────────────────────────────
apt-get update -y
apt-get install -y docker.io docker-compose curl postgresql-client

systemctl enable docker
systemctl start docker

# ── 1b. Swap ────────────────────────────────────────────────────────────────────
# t3.micro has only 1 GB RAM and no swap by default -- api+worker+scheduler
# containers alone leave very little headroom, and a Playwright/Chromium
# instance (for account registration/login) can tip it into OOM. 1 GB swap
# gives breathing room without resizing the instance.
if [ ! -f /swapfile ]; then
  fallocate -l 1G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ── 2. Directory structure ─────────────────────────────────────────────────────
mkdir -p /opt/app

# ── 3. Write .env.production ───────────────────────────────────────────────────
# NOTE: The placeholders below are Terraform template substitutions — they
# resolve to actual secret values before this script is sent to EC2.
# AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY are deliberately left unset — the
# app authenticates to SQS via the EC2 instance's IAM role instead.
cat > /opt/app/.env.production << ENVEOF
DATABASE_URL=${database_url}
QUEUE_BACKEND=sqs
AWS_SQS_QUEUE_URL=${aws_sqs_queue_url}
AWS_REGION=${aws_region}
ACCOUNT_ENCRYPTION_KEY=${account_encryption_key}
API_KEY=${api_key}
PROJECT_NAME=Viralytics
DEBUG=False
LOG_LEVEL=INFO
ENVEOF

chmod 600 /opt/app/.env.production

# ── 3b. Create the app database on the existing RDS instance if it doesn't
# exist yet ─────────────────────────────────────────────────────────────────────
# viralytics-db is a shared, pre-existing instance (not created by this stack) —
# this only creates the one database this app uses, idempotently, so re-running
# bootstrap (or a second EC2) never fails on "database already exists."
if ! PGPASSWORD='${db_password}' psql -h '${db_host}' -U '${db_username}' -d postgres -tAc \
     "SELECT 1 FROM pg_database WHERE datname = '${db_name}'" | grep -q 1; then
  PGPASSWORD='${db_password}' psql -h '${db_host}' -U '${db_username}' -d postgres -c \
    "CREATE DATABASE ${db_name}"
fi

# ── 4. Write docker-compose.prod.yml ──────────────────────────────────────────
cat > /opt/app/docker-compose.prod.yml << 'COMPOSEEOF'
services:
  migrate:
    image: ghcr.io/${ghcr_username}/dosomething-scraper-api:latest
    container_name: dosomething_scraper_migrate
    env_file:
      - /opt/app/.env.production
    command: ["uv", "run", "alembic", "upgrade", "head"]
    restart: "no"

  api:
    image: ghcr.io/${ghcr_username}/dosomething-scraper-api:latest
    container_name: dosomething_scraper_api
    restart: unless-stopped
    env_file:
      - /opt/app/.env.production
    ports:
      - "8000:8000"     # security group already restricts this to admin_cidr_block
    depends_on:
      migrate:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 20s
    # This VPC has no IPv6 route -- without this, Chromium/httpx resolve
    # Instagram's AAAA record, try to connect over IPv6, and hang until timeout.
    sysctls:
      - net.ipv6.conf.all.disable_ipv6=1
      - net.ipv6.conf.default.disable_ipv6=1

  worker:
    image: ghcr.io/${ghcr_username}/dosomething-scraper-worker:latest
    container_name: dosomething_scraper_worker
    restart: unless-stopped
    env_file:
      - /opt/app/.env.production
    depends_on:
      migrate:
        condition: service_completed_successfully
    sysctls:
      - net.ipv6.conf.all.disable_ipv6=1
      - net.ipv6.conf.default.disable_ipv6=1

  scheduler:
    image: ghcr.io/${ghcr_username}/dosomething-scraper-scheduler:latest
    container_name: dosomething_scraper_scheduler
    restart: unless-stopped
    env_file:
      - /opt/app/.env.production
    depends_on:
      migrate:
        condition: service_completed_successfully
    sysctls:
      - net.ipv6.conf.all.disable_ipv6=1
      - net.ipv6.conf.default.disable_ipv6=1

  watchtower:
    image: containrrr/watchtower:latest
    container_name: dosomething_scraper_watchtower
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /root/.docker:/config:ro
    environment:
      - DOCKER_CONFIG=/config
      - WATCHTOWER_POLL_INTERVAL=60
      - WATCHTOWER_CLEANUP=true
      - WATCHTOWER_ROLLING_RESTART=true
    command: dosomething_scraper_api dosomething_scraper_worker dosomething_scraper_scheduler
COMPOSEEOF

# ── 5. Authenticate Docker with GHCR ──────────────────────────────────────────
# Writes credentials to /root/.docker/config.json — mounted into Watchtower.
echo "${ghcr_token}" | docker login ghcr.io -u "${ghcr_username}" --password-stdin

# ── 6. Pull images and start ───────────────────────────────────────────────────
cd /opt/app
docker pull ghcr.io/${ghcr_username}/dosomething-scraper-api:latest
docker pull ghcr.io/${ghcr_username}/dosomething-scraper-worker:latest
docker pull ghcr.io/${ghcr_username}/dosomething-scraper-scheduler:latest

docker-compose -f docker-compose.prod.yml up -d

# ── 7. Confirm status ───────────────────────────────────────────────────────────
echo ""
echo "=== Bootstrap COMPLETE: $(date) ==="
echo ""
echo "Running containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "================================================================"
echo "  Next: register at least one Instagram account before scraping:"
echo "    ssh -i <key>.pem ubuntu@<this-ip>"
echo "    docker exec -it dosomething_scraper_worker uv run python scripts/register_instagram_account.py --username <handle>"
echo "    (must run in the 'worker' container -- it's the one with Playwright/Chromium installed)"
echo "================================================================"
