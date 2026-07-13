# ── Latest Ubuntu 22.04 LTS AMI (Canonical) ──────────────────────────────────
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical's official AWS account

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ── Security Group ─────────────────────────────────────────────────────────────
# SSH and the raw API port stay restricted to admin_cidr_block. Ports 80/443
# are the one deliberately public exception — engine.viralytics.in (via
# Cloudflare) reverse-proxies through the `dashboard` (Caddy) service on this
# box, which also needs 80 reachable for Let's Encrypt ACME validation.
resource "aws_security_group" "app_sg" {
  name = "dosomething-scraper-sg"
  # description is ForceNew in the AWS provider (changing it destroys and
  # recreates the security group) -- since this SG is attached to the live,
  # running EC2 instance's ENI, AWS refuses that delete (DependencyViolation)
  # and Terraform hangs for the full delete timeout before failing. Left
  # exactly as originally created; the ingress rules below are free-form
  # in-place updates and don't have this problem.
  description = "DoSomething-scraper: allow SSH and API access from admin CIDR only"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.admin_cidr_block]
  }

  ingress {
    description = "API (admin/dispatch endpoints)"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [var.admin_cidr_block]
  }

  ingress {
    description = "HTTP - dashboard (Caddy) + Lets Encrypt ACME challenge"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS - dashboard (Caddy), engine.viralytics.in"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name    = "dosomething-scraper-sg"
    Project = "DoSomething-scraper"
  }
}

# ── EC2 Instance ───────────────────────────────────────────────────────────────
resource "aws_instance" "app" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  key_name                    = var.key_pair_name
  subnet_id                   = data.aws_subnets.default.ids[0]
  vpc_security_group_ids      = [aws_security_group.app_sg.id]
  iam_instance_profile        = aws_iam_instance_profile.scraper_ec2_profile.name
  associate_public_ip_address = true

  # user_data is a Terraform templatefile — it runs ONCE on first boot.
  # It installs Docker, writes .env.production, starts docker-compose.
  user_data = templatefile("${path.module}/user_data.sh", {
    ghcr_username = var.ghcr_username
    ghcr_token    = var.ghcr_token

    database_url          = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${data.aws_db_instance.existing.address}:5432/${var.db_name}"
    database_url_readonly = "postgresql+asyncpg://${var.readonly_db_username}:${var.readonly_db_password}@${data.aws_db_instance.existing.address}:5432/${var.db_name}"
    db_host               = data.aws_db_instance.existing.address
    db_username           = var.db_username
    db_password           = var.db_password
    db_name               = var.db_name
    readonly_db_username  = var.readonly_db_username
    readonly_db_password  = var.readonly_db_password

    aws_region             = var.aws_region
    aws_sqs_queue_url      = aws_sqs_queue.scrape_jobs.url
    account_encryption_key = var.account_encryption_key
    api_key                = var.api_key
  })

  root_block_device {
    volume_size           = 30 # GB — Playwright/Chromium image + Docker layers add up
    volume_type           = "gp3"
    delete_on_termination = true
  }

  # IMPORTANT: Prevent Terraform from replacing the instance on re-runs.
  # user_data only runs on FIRST BOOT — changes here don't auto-apply to a running EC2.
  lifecycle {
    ignore_changes = [ami, user_data]
  }

  tags = {
    Name    = "dosomething-scraper"
    Project = "DoSomething-scraper"
  }

  # user_data creates the app database over this SG rule on first boot —
  # make sure the rule exists before the instance launches, not just app_sg itself.
  depends_on = [aws_security_group_rule.rds_from_app]
}

# ── Public IP output note ──────────────────────────────────────────────────────
# An Elastic IP (13.206.31.71) has been manually allocated and associated to
# this instance outside of Terraform (engine.viralytics.in points at it via
# Cloudflare) — this stack has no aws_eip resource, so Terraform has no
# opinion on it and won't touch it. aws_instance.app.public_ip reflects the
# EIP automatically once associated. Import it as a proper aws_eip resource
# if you want Terraform to manage it directly.
