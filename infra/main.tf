terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # S3 backend for state storage.
  # 'bucket' and 'region' are NOT set here — they are passed at init time via:
  #   terraform init -backend-config="bucket=YOUR_BUCKET" -backend-config="region=YOUR_REGION"
  # Same bucket DoSomething-be uses is fine — the 'key' below keeps state separate.
  backend "s3" {
    key = "dosomething-scraper/terraform.tfstate"
  }
}

provider "aws" {
  region = var.aws_region
}

# ── Default VPC/subnet — no dedicated VPC needed for a single-box deployment ──
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}
