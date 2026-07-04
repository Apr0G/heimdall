# =============================================================================
# RDS PHI-readiness — backups, deletion protection, final snapshot, and enforced
# TLS. All gated behind rds_production so you flip them on together during a
# maintenance window (attaching the parameter group needs one reboot). Applying
# with the default (false) changes nothing.
# =============================================================================

variable "rds_production" {
  description = "true = enable backups/PITR, deletion protection, final snapshot, and rds.force_ssl (attaching the parameter group requires a one-time reboot)."
  type        = bool
  default     = false
}

variable "rds_parameter_group_family" {
  description = "Must match the DB's Postgres major version (DB is on 18.3)."
  type        = string
  default     = "postgres18"
}

# Forces every DB connection to use TLS (defense-in-depth; the app already sets
# ssl=require in DATABASE_URL). Attached to the instance only when rds_production.
resource "aws_db_parameter_group" "heimdall" {
  name        = "heimdall-pg"
  family      = var.rds_parameter_group_family
  description = "Heimdall Postgres params — enforce TLS"

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }
}
