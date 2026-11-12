# =============================================================================
# RDS network lockdown — give the database its own security group that trusts
# ONLY the backend's ECS tasks, and take it off the public internet.
#
# Two-phase apply, so the risky part is easily reversible:
#   Phase A (rds_private = false): swap the DB's firewall to trust only
#     the backend. Public + laptop can no longer connect (firewall blocks them),
#     but the public endpoint still exists — so rollback is trivial. This is the
#     real test of the private path.
#   Phase B (rds_private = true, default): also remove the public endpoint entirely.
#
# The cutover is DONE and verified (RESOLVED 2026-07-08), so true is the default
# — an apply that omits the variable must never re-publish the PHI endpoint
# (same reasoning as rds_production in rds-hardening.tf). false stays available
# for an explicit throwaway environment only.
# =============================================================================

variable "rds_private" {
  description = "true (default) = no public endpoint, backend-only — the private cutover is verified, so a PHI endpoint must never be re-published by omission. false = firewall-locked but public endpoint kept (explicit throwaway/rollback use only)."
  type        = bool
  default     = true
}

# The security group Amazon ECS Express assigned to the backend tasks. RDS will
# trust exactly this and nothing else. Looked up by name so it survives ID churn.
data "aws_security_group" "ecs_tasks" {
  vpc_id = data.aws_vpc.default.id
  filter {
    name   = "group-name"
    values = ["default-heimdall-api-vpc-00000000000000000"]
  }
}

# The database's own security group: Postgres, only from the backend tasks.
resource "aws_security_group" "rds" {
  name        = "heimdall-rds"
  description = "Postgres access for Heimdall - backend ECS tasks only"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "Postgres from the Heimdall backend tasks"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [data.aws_security_group.ecs_tasks.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
