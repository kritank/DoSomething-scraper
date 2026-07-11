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
# No public domain/nginx in front of this box (internal admin tool) — SSH and
# the API port are both restricted to admin_cidr_block, not opened publicly.
resource "aws_security_group" "app_sg" {
  name        = "dosomething-scraper-sg"
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

    database_url           = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${aws_db_instance.scraper.address}:5432/${var.db_name}"
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

  depends_on = [aws_db_instance.scraper]
}

# ── Public IP output note ──────────────────────────────────────────────────────
# No pre-allocated Elastic IP: unlike DoSomething-be, there's no DNS record
# pointing here, so a stable IP isn't required. The default VPC assigns a
# public IP automatically; it will change only if the instance is stopped and
# restarted (it won't on a reboot). Add an aws_eip if you want it pinned.
