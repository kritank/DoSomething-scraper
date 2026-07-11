# ── AWS Infrastructure ────────────────────────────────────────────────────────

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "ap-south-1" # Mumbai — matches DoSomething-be
}

variable "instance_type" {
  description = "EC2 instance type. NOTE: t3.micro (1 GB RAM) risks OOM running api+worker+scheduler+Playwright/Chromium together on one box — t3.small (2 GB) is the safer default if cost allows."
  type        = string
  default     = "t3.micro"
}

variable "key_pair_name" {
  description = "Name of the existing AWS EC2 Key Pair for SSH access (created manually in AWS Console)"
  type        = string
}

variable "admin_cidr_block" {
  description = "CIDR allowed to reach SSH (22) and the API (8000) — set this to YOUR_IP/32. There is no public domain/nginx in front of this box, so leaving this open (0.0.0.0/0) exposes the admin API to the internet."
  type        = string
}

# ── GHCR Authentication ───────────────────────────────────────────────────────
# Used by Watchtower on EC2 to pull new images from GitHub Container Registry.

variable "ghcr_username" {
  description = "GitHub username for GHCR auth (e.g. ambujalpha)"
  type        = string
}

variable "ghcr_token" {
  description = "GitHub Personal Access Token with read:packages scope"
  type        = string
  sensitive   = true
}

# ── RDS (PostgreSQL) ───────────────────────────────────────────────────────────
# This stack does NOT create an RDS instance — it connects to the existing
# "viralytics-db" instance (see rds.tf). These are that instance's actual
# credentials, not values used to provision anything.

variable "db_name" {
  description = "Database name on the existing viralytics-db instance — created automatically by user_data.sh on first EC2 boot if it doesn't already exist"
  type        = string
  default     = "viralytics_scrapper"
}

variable "db_username" {
  description = "Username on the existing viralytics-db instance (its actual master user is \"postgres\", not a custom user)"
  type        = string
  default     = "postgres"
}

variable "db_password" {
  description = "Password for db_username on the existing viralytics-db instance"
  type        = string
  sensitive   = true
}

# ── SQS ────────────────────────────────────────────────────────────────────────

variable "sqs_queue_name" {
  description = "Name of the SQS queue used for scrape jobs"
  type        = string
  default     = "viralytics-scrape-jobs"
}

# ── App Environment Variables ─────────────────────────────────────────────────
# These are written to /opt/app/.env.production on the EC2 instance at boot.
# All are marked sensitive so they never appear in Terraform output or logs.

variable "account_encryption_key" {
  description = "Fernet key encrypting Instagram session cookies at rest (generate with `python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"`)"
  type        = string
  sensitive   = true
}

variable "api_key" {
  description = "Shared-secret API key protecting all endpoints (M2M auth)"
  type        = string
  sensitive   = true
}
