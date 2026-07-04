# =============================================================================
# RDS network lockdown — give the database its own security group that trusts
# ONLY the backend's ECS tasks, and take it off the public internet.
#
# Two-phase apply (see DEPLOY.md), so the risky part is easily reversible:
#   Phase A (rds_private = false, default): swap the DB's firewall to trust only
#     the backend. Public + laptop can no longer connect (firewall blocks them),
#     but the public endpoint still exists — so rollback is trivial. This is the
#     real test of the private path.
#   Phase B (rds_private = true): also remove the public endpoint entirely.
# =============================================================================

variable "rds_private" {
  description = "false = firewall-locked to the backend (public endpoint kept but blocked — reversible test); true = also remove the public endpoint."
  type        = bool
  default     = false
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
  description = "Postgres access for Heimdall — backend ECS tasks only"
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
