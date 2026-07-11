# ── IAM Role for EC2 → SQS access ─────────────────────────────────────────────
# The app authenticates to SQS via this instance role (see app/queue/sqs_queue.py) --
# no static AWS_ACCESS_KEY_ID/SECRET on disk.

data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scraper_ec2_role" {
  name               = "dosomething-scraper-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json

  tags = {
    Project = "DoSomething-scraper"
  }
}

data "aws_iam_policy_document" "sqs_access" {
  statement {
    sid = "ScrapeQueueAccess"
    actions = [
      "sqs:SendMessage",
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
    ]
    resources = [
      aws_sqs_queue.scrape_jobs.arn,
      aws_sqs_queue.scrape_jobs_dlq.arn,
    ]
  }
}

resource "aws_iam_role_policy" "sqs_access" {
  name   = "sqs-access"
  role   = aws_iam_role.scraper_ec2_role.id
  policy = data.aws_iam_policy_document.sqs_access.json
}

resource "aws_iam_instance_profile" "scraper_ec2_profile" {
  name = "dosomething-scraper-ec2-profile"
  role = aws_iam_role.scraper_ec2_role.name
}
