# ── AWS Infrastructure ────────────────────────────────────────────────────────

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "ap-south-1" # Mumbai — matches DoSomething-be
}

variable "instance_type" {
  description = "EC2 instance type. t3.small (2 GB RAM) — api+worker+scheduler+Playwright/Chromium together need more headroom than t3.micro."
  type        = string
  default     = "t3.small"
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

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "viralytics"
}

variable "db_username" {
  description = "Master DB username"
  type        = string
  default     = "viralytics_admin"
}

variable "db_password" {
  description = "Master DB password"
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
