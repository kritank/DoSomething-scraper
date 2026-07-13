output "ec2_public_ip" {
  description = "Public IP of the EC2 instance — a manually-associated Elastic IP (13.206.31.71), not managed by this Terraform stack"
  value       = aws_instance.app.public_ip
}

output "ec2_instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.app.id
}

output "rds_endpoint" {
  description = "RDS instance endpoint (host:port) — existing viralytics-db instance, not created by this stack"
  value       = data.aws_db_instance.existing.endpoint
}

output "sqs_queue_url" {
  description = "SQS queue URL used for scrape jobs"
  value       = aws_sqs_queue.scrape_jobs.url
}

output "ssh_command" {
  description = "SSH command to connect to the EC2 instance"
  value       = "ssh -i <your-key>.pem ubuntu@${aws_instance.app.public_ip}"
}

output "api_url" {
  description = "API base URL (reachable only from admin_cidr_block)"
  value       = "http://${aws_instance.app.public_ip}:8000"
}

output "dashboard_url" {
  description = "Public dashboard URL — served by the `dashboard` (Caddy) service, fronted by Cloudflare"
  value       = "https://engine.viralytics.in"
}

output "next_steps" {
  description = "What to do after provisioning"
  value       = <<-EOT
    ✅ EC2 and SQS are provisioned (RDS reuses the existing viralytics-db
    instance). Bootstrap ran automatically on first boot (migrations applied,
    containers started).

    STEP 1 — Verify:
      curl http://${aws_instance.app.public_ip}:8000/health

    STEP 2 — Register at least one Instagram account (required before any scrape runs):
      ssh -i <your-key>.pem ubuntu@${aws_instance.app.public_ip}
      docker exec -it dosomething_scraper_worker uv run python scripts/register_instagram_account.py --username <handle>

    STEP 3 — Seed categories/influencers and trigger a scrape via the admin API
      (see README.md — POST /api/v1/admin/influencers, POST /api/v1/admin/scrape).
      All /admin routes require an X-API-Key header matching API_KEY (see
      app/core/security.py), on top of the security group restricting :8000
      to admin_cidr_block.

    STEP 4 — Open the ops dashboard:
      https://engine.viralytics.in
      Served directly from this box by the `dashboard` (Caddy) service --
      enter your API_KEY when prompted (ApiKeyGate), stored in the browser's
      localStorage from there on.
  EOT
}
