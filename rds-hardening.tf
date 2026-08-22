# =============================================================================
# RDS PHI-readiness — backups, deletion protection, final snapshot, and enforced
# TLS. All gated behind rds_production. The SAFE posture is the default: an
# apply that omits the variable gets backups, deletion protection, a final
# snapshot and force_ssl. Set it to false only for a throwaway environment.
# =============================================================================

variable "rds_production" {
  description = "true (default) = backups/PITR, deletion protection, final snapshot, rds.force_ssl. false only for disposable environments — a PHI database must never be applied without these by omission."
  type        = bool
  default     = true
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
  description = "Heimdall Postgres params - enforce TLS"

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }
}
