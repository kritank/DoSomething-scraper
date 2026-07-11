# Viralytics

**Viralytics** is a production-grade Instagram Influencer Intelligence Platform. It continuously collects public data from Instagram, computes category-specific benchmarks (e.g., Fitness, Finance, Food), and generates actionable recommendations for creators to improve their content strategy.

*Note: This is an intelligence and analytics platform, not an influencer marketplace.*

---

## 🏗 Architecture

Viralytics is composed of three primary services running concurrently:

1. **API Service (`main.py`)**: A high-performance FastAPI server providing REST endpoints for dashboards, admin controls, and fetching computed recommendations.
2. **Worker Process (`app/workers/worker_runner.py`)**: Asynchronous workers consuming the job queue, scraping Instagram via HTTPX, running NLP feature extraction, and updating the database.
3. **Scheduler (`app/scheduler/runner.py`)**: A lightweight cron-based trigger (APScheduler) that dispatches daily scraping jobs for all active influencers.

### Tech Stack
- **Web Framework**: FastAPI (Python 3.13)
- **Database**: PostgreSQL with asyncpg & SQLAlchemy 2.0
- **Migrations**: Alembic
- **Queue Layer**: Redis (Local/Dev) or Amazon SQS (Production)
- **Dependency Management**: `uv`
- **Containerization**: Docker & Docker Compose

---

## 🚀 Features

- **Asynchronous Scraping Engine**: Mimics mobile API requests for rapid, low-latency data fetching. Includes rate limit backoffs and error handling.
- **NLP & Feature Extraction**: Analyzes captions to extract hashtags, mentions, emoji counts, language, and calls-to-action (CTAs).
- **Benchmarking Engine**: Aggregates influencer metrics at the category level (e.g., average engagement rates, optimal posting hours).
- **Recommendation Engine**: Generates targeted, actionable tasks for individual influencers by comparing their recent performance against category benchmarks.
- **Queue Abstraction**: Pluggable backend seamlessly switches between Redis (for cheap local dev) and Amazon SQS (for resilient production deployments).

---

## 🛠 Local Setup & Development

### 1. Prerequisites
- Docker and Docker Compose
- Python 3.13 (if running outside Docker)
- `uv` (for fast Python dependency management)

### 2. Environment Variables
Copy the `.env.example` file to `.env`:
```bash
cp .env.example .env
```
Set `ACCOUNT_ENCRYPTION_KEY` (used to encrypt Instagram session cookies at rest):
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Instagram accounts themselves are no longer pasted into `.env` -- see "Registering Instagram Accounts" below.

### 3. Start Infrastructure
Start the database and Redis queue:
```bash
docker compose up -d postgres redis
```

### 4. Database Migrations
Before starting the API or workers, initialize the database schema:
```bash
# Create a virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
uv sync --dev

# Generate the initial schema migration (if not already done)
alembic revision --autogenerate -m "initial_schema"

# Apply migrations
alembic upgrade head
```

### 5. Register Instagram Accounts
The scraper draws from a pool of Instagram accounts stored in the `instagram_accounts`
table instead of a single hardcoded session in `.env`. Register at least one before
running any scrape -- workers will fail fast with "no healthy Instagram accounts
available" otherwise. This drives a real (Playwright) login, so it can hit a 2FA/
"suspicious login" checkpoint that has to be cleared manually in a real browser first:
```bash
uv run python scripts/register_instagram_account.py --username your_scraper_account
```
You'll be prompted for the password (prefer this over `--password` on the command line,
which lands in shell history). Register more than one account to spread load across the
pool -- each gets its own persistent user-agent and locale/timezone pairing.

### 6. Run the Application
You can run the entire stack (API, Worker, Scheduler, DB, Queue, Nginx) via Docker Compose:
```bash
docker compose up --build
```
Alternatively, to run the API locally with hot-reloading:
```bash
./scripts/dev.sh
```

To seed sample categories and influencers, then scrape them immediately:
```bash
PYTHONPATH=.venv/lib/python3.13/site-packages /Users/kritank/.local/share/uv/python/cpython-3.13.14-macos-aarch64-none/bin/python3.13 scripts/seed_and_scrape.py
```
To seed records only, skip scraping:
```bash
PYTHONPATH=.venv/lib/python3.13/site-packages /Users/kritank/.local/share/uv/python/cpython-3.13.14-macos-aarch64-none/bin/python3.13 scripts/seed_and_scrape.py --seed-only
```

---

## 📚 API Overview

The API is accessible at `http://localhost:8000`. 
Interactive Swagger documentation is available at `http://localhost:8000/docs`.

### Key Endpoints

- `GET /health` & `GET /ready`: Infrastructure health checks.
- `POST /api/v1/admin/categories`: Create a new influencer category.
- `POST /api/v1/admin/influencers`: Register a new influencer handle.
- `POST /api/v1/admin/scrape?influencer_id=...`: Manually trigger a scrape job for an influencer.
- `GET /api/v1/benchmarks/{category_id}`: Fetch the latest computed benchmark for a category.
- `GET /api/v1/recommendations/{influencer_id}`: Fetch personalized recommendations for an influencer.

---

## 🧪 Testing

Viralytics uses `pytest` for unit and integration testing. Tests can be run via `uv`:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/
```

---

## 📦 Deployment

Deployment is fully automated, matching the DoSomething-be/DoSomething-Meta pattern:

1. **`.github/workflows/build-push.yml`** builds the `api`/`worker`/`scheduler` images
   and pushes them to GHCR (`ghcr.io/ambujalpha/dosomething-scraper-{api,worker,scheduler}`)
   on every push to `main` — i.e. every PR merge. Only a `main` push produces the
   `:latest` tag that production actually tracks.
2. **`infra/`** is a Terraform stack (own EC2 + RDS Postgres + SQS + IAM — a
   separate box from DoSomething-be, since this service has its own schema,
   its own long-running worker/scheduler processes, and no public frontend).
   Provision it via the **`infra.yml`** workflow (`workflow_dispatch`, choose
   `plan`/`apply`/`destroy`) — see `infra/variables.tf` for the GitHub secrets
   it needs (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`,
   `TF_STATE_BUCKET`, `EC2_KEY_PAIR_NAME`, `ADMIN_CIDR_BLOCK`, `GHCR_TOKEN`,
   `DB_PASSWORD`, `ACCOUNT_ENCRYPTION_KEY`, `API_KEY`).
3. On the box, **Watchtower** polls GHCR every 60s and auto-restarts any of
   the three containers once a new `:latest` image lands — so a merged PR is
   live within roughly a minute of the build finishing.

There's no public domain/nginx in front of this box (it's an internal
API + background worker, not a public-facing app) — the API port (8000) and
SSH are both restricted at the security-group level to `admin_cidr_block`.

`docker-compose.prod.yml` at the repo root mirrors what Terraform's
`infra/user_data.sh` deploys (SQS instead of Redis, RDS instead of local
Postgres, a one-shot `migrate` service that runs `alembic upgrade head`
before `api`/`worker`/`scheduler` start) — the deployed version on EC2 pulls
prebuilt GHCR images; this local copy builds from source, useful for testing
the prod configuration before merging.

After the first `terraform apply`, register at least one Instagram account —
workers fail fast with "no healthy Instagram accounts available" otherwise:
```bash
ssh -i <key>.pem ubuntu@<ec2-ip>
docker exec -it dosomething_scraper_worker uv run python scripts/register_instagram_account.py --username <handle>
```
(Must run in the `worker` container — it's the one with Playwright/Chromium installed.)
