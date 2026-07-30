# =============================================================================
# Least-privilege runtime DB role (heimdall_app) — review HIGH #11.
#
# The app connects as heimdall_app (limited); migrations run as the owner
# (heimdall_admin) via a DEDICATED migrate task definition so the admin URL never
# lands in the app's environment or IAM. Staged cutover:
#   1. apply (app_db_role_active = false)  -> creates secrets + migrate task def
#   2. run migrate-db                      -> migration 0007 creates the role
#   3. verify heimdall_app works (one-off) -> gate before cutover
#   4. apply (app_db_role_active = true)   -> app repoints to heimdall_app
# =============================================================================

variable "app_db_role_active" {
  description = "When true, the app service connects as heimdall_app (requires migration 0007 applied first). Staged cutover flag; keep false until the role is created and verified."
  type        = bool
  default     = false
}

# Alphanumeric so it is a safe SQL literal in migration 0007 (special = false).
resource "random_password" "app_db" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "app_db_password" {
  name        = "heimdall/app-db-password"
  description = "Password for the least-privilege heimdall_app DB role (used by migration 0007)."
  kms_key_id  = aws_kms_key.heimdall.arn
}

resource "aws_secretsmanager_secret_version" "app_db_password" {
  secret_id     = aws_secretsmanager_secret.app_db_password.id
  secret_string = random_password.app_db.result
}

# Secret pepper for HMAC-keyed identifier hashes: cases.member_id_hash and the
# corpus export's claim_ref. A bare SHA-256 of a short, structured, payer-prefixed
# identifier is exhaustible offline, so it is not a de-identification control under
# §164.514 — and §164.514(c) separately requires a re-identification code that is
# not derived from information about the individual. Keeping the key OUT of the
# database is the whole point: a DB dump alone then reveals nothing.
#
# ROTATION breaks linkage by design. member_id_hash currently has no readers, so
# rotating it costs nothing today; an already-exported corpus keeps the claim_ref
# values it was written with, and a re-export produces different ones.
resource "random_password" "phi_hash_pepper" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "phi_hash_pepper" {
  name        = "heimdall/phi-hash-pepper"
  description = "HMAC pepper for member_id_hash and corpus claim_ref (see core/hashing.py)."
  kms_key_id  = aws_kms_key.heimdall.arn
}

resource "aws_secretsmanager_secret_version" "phi_hash_pepper" {
  secret_id     = aws_secretsmanager_secret.phi_hash_pepper.id
  secret_string = random_password.phi_hash_pepper.result
}

resource "aws_secretsmanager_secret" "app_database_url" {
  name        = "heimdall/app-database-url"
  description = "SQLAlchemy asyncpg connection string for the app (heimdall_app, limited)."
  kms_key_id  = aws_kms_key.heimdall.arn
}

resource "aws_secretsmanager_secret_version" "app_database_url" {
  secret_id = aws_secretsmanager_secret.app_database_url.id
  secret_string = format(
    "postgresql+asyncpg://heimdall_app:%s@%s:5432/%s?ssl=require",
    random_password.app_db.result,
    aws_db_instance.heimdall.address,
    aws_db_instance.heimdall.db_name,
  )
}

# --- Migrate task definition (owner creds; not the app's task def) -----------
resource "aws_cloudwatch_log_group" "migrate" {
  name              = "/aws/ecs/heimdall-migrate"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.heimdall.arn
}

resource "aws_iam_role" "migrate_exec" {
  name = "heimdall-migrate-exec"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "migrate_exec" {
  name = "heimdall-migrate-exec"
  role = aws_iam_role.migrate_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EcrPull"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid      = "EcrImage"
        Effect   = "Allow"
        Action   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
        Resource = aws_ecr_repository.backend.arn
      },
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.migrate.arn}:*"
      },
      {
        Sid    = "Secrets"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue", "kms:Decrypt"]
        Resource = [
          aws_secretsmanager_secret.database_url.arn,    # admin URL (owner) for alembic
          aws_secretsmanager_secret.app_db_password.arn, # heimdall_app password for 0007
          aws_kms_key.heimdall.arn,
        ]
      },
    ]
  })
}

resource "aws_ecs_task_definition" "migrate" {
  family                   = "heimdall-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.migrate_exec.arn

  container_definitions = jsonencode([{
    name      = "migrate"
    image     = "${aws_ecr_repository.backend.repository_url}:latest"
    essential = true
    command   = ["alembic", "upgrade", "head"]
    environment = [
      { name = "AWS_REGION", value = "us-east-1" },
      { name = "APP_ENV", value = "production" },
    ]
    secrets = [
      { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.database_url.arn },
      { name = "APP_DB_PASSWORD", valueFrom = aws_secretsmanager_secret.app_db_password.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.migrate.name
        "awslogs-region"        = "us-east-1"
        "awslogs-stream-prefix" = "migrate"
      }
    }
  }])
}
