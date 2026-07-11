# ── SQS Queue — scrape job messages ───────────────────────────────────────────
resource "aws_sqs_queue" "scrape_jobs_dlq" {
  name                      = "${var.sqs_queue_name}-dlq"
  message_retention_seconds = 1209600 # 14 days — max, gives time to inspect/replay failures

  tags = {
    Name    = "${var.sqs_queue_name}-dlq"
    Project = "DoSomething-scraper"
  }
}

resource "aws_sqs_queue" "scrape_jobs" {
  name = var.sqs_queue_name

  # Comment/reply sync on a large post history can run for many minutes
  # (observed ~13 min for a single job in testing) — visibility_timeout must
  # comfortably exceed the slowest realistic job, or SQS redelivers the
  # message to another worker while the first is still processing it.
  visibility_timeout_seconds = 1800   # 30 min, matches ACCOUNT_LEASE_TIMEOUT_S
  message_retention_seconds  = 345600 # 4 days

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.scrape_jobs_dlq.arn
    maxReceiveCount     = 5
  })

  tags = {
    Name    = var.sqs_queue_name
    Project = "DoSomething-scraper"
  }
}
