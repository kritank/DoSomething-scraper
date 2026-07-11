# ── RDS PostgreSQL ─────────────────────────────────────────────────────────────

resource "aws_db_subnet_group" "scraper" {
  name       = "dosomething-scraper-db-subnet-group"
  subnet_ids = data.aws_subnets.default.ids

  tags = {
    Name    = "dosomething-scraper-db-subnet-group"
    Project = "DoSomething-scraper"
  }
}

# Ingress only from the app's own security group — never opened to the internet.
resource "aws_security_group" "rds_sg" {
  name        = "dosomething-scraper-rds-sg"
  description = "DoSomething-scraper: allow Postgres only from the app EC2 instance"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "Postgres from app EC2"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name    = "dosomething-scraper-rds-sg"
    Project = "DoSomething-scraper"
  }
}

resource "aws_db_instance" "scraper" {
  identifier     = "dosomething-scraper-db"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_allocated_storage * 2 # allow modest storage autoscaling
  storage_type          = "gp3"

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.scraper.name
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
  publicly_accessible    = false

  backup_retention_period   = 7
  skip_final_snapshot       = false
  final_snapshot_identifier = "dosomething-scraper-db-final"
  deletion_protection       = true

  tags = {
    Name    = "dosomething-scraper-db"
    Project = "DoSomething-scraper"
  }
}
