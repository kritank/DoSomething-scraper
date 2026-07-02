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
Open `.env` and fill in your Instagram session cookies. You must extract these from an active, logged-in Instagram session in your browser:
- `INSTAGRAM_SESSION_ID` (`sessionid`)
- `INSTAGRAM_CSRF_TOKEN` (`csrftoken`)
- `INSTAGRAM_DS_USER_ID` (`ds_user_id`)
- `INSTAGRAM_IG_DID` (`ig_did` - optional but recommended)

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

### 5. Run the Application
You can run the entire stack (API, Worker, Scheduler, DB, Queue, Nginx) via Docker Compose:
```bash
docker compose up --build
```
Alternatively, to run the API locally with hot-reloading:
```bash
uv run uvicorn main:app --reload
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
uv run pytest tests/
```

---

## 📦 Deployment

A `docker-compose.prod.yml` is provided for production environments (e.g., AWS EC2). 
The production configuration:
- Disables the local Postgres and Redis containers.
- Expects `DATABASE_URL` to point to a managed database (like Amazon RDS).
- Expects `QUEUE_BACKEND=sqs` and valid AWS credentials for Amazon SQS.
- Configures Nginx with TLS/SSL certificate mounting points.