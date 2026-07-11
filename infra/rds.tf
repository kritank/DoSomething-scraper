# ── RDS PostgreSQL ─────────────────────────────────────────────────────────────
# Reuses the existing "viralytics-db" instance rather than creating a new one —
# it was already provisioned for this project. We only add a security-group
# rule granting the new app EC2 instance access to it.

data "aws_db_instance" "existing" {
  db_instance_identifier = "viralytics-db"
}

# The existing instance's own security group (viralytics-rds-sg) already has
# ingress from another SG (its original app instance, if any). We add ours
# alongside it rather than replacing/managing the whole security group, since
# that SG isn't owned by this Terraform state.
resource "aws_security_group_rule" "rds_from_app" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = "sg-013c2c72999a34b34" # viralytics-rds-sg
  source_security_group_id = aws_security_group.app_sg.id
  description              = "Postgres from dosomething-scraper app EC2"
}
