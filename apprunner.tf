# =============================================================================
# Stage 2 — Backend on AWS App Runner (builds from GitHub source, no Docker).
#
# LEAN: App Runner reaches RDS over its existing (public, TLS) endpoint, so
# nothing here changes database networking. Making RDS private + routing App
# Runner through a VPC connector is Stage 5 (a coordinated cutover).
#
# Review `terraform plan` before `apply`. Requires three tfvars values you set:
# apprunner_connection_arn, bedrock_model_id, and (later) frontend_url.
# =============================================================================

variable "apprunner_connection_arn" {
  description = "ARN of the App Runner GitHub connection (create it once in the App Runner console, then paste the ARN into terraform.tfvars)."
  type        = string
}

variable "github_repo_url" {
  description = "HTTPS URL of the repo App Runner builds from."
  type        = string
  default     = "https://github.com/Apr0G/heimdall"
}

variable "app_branch" {
  description = "Branch App Runner deploys and auto-redeploys from."
  type        = string
  default     = "main"
}

variable "bedrock_model_id" {
  description = "Bedrock inference-profile id (starts with 'us.'), same value as local .env.local."
  type        = string
}

variable "frontend_url" {
  description = "Public URL of the Vercel frontend, used for CORS. Set to the Vercel URL in Stage 4; the localhost default is a safe placeholder until then."
  type        = string
  default     = "http://localhost:3000"
}

# --- Full DB connection string, stored as a secret and injected masked --------
resource "aws_secretsmanager_secret" "database_url" {
  name        = "heimdall/database-url"
  description = "SQLAlchemy asyncpg connection string for the backend."
  kms_key_id  = aws_kms_key.heimdall.arn
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id = aws_secretsmanager_secret.database_url.id
  secret_string = format(
    "postgresql+asyncpg://%s:%s@%s:5432/%s?ssl=require",
    aws_db_instance.heimdall.username,
    var.db_password,
    aws_db_instance.heimdall.address,
    aws_db_instance.heimdall.db_name,
  )
}

# --- App Runner service -------------------------------------------------------
resource "aws_apprunner_service" "backend" {
  service_name = "heimdall-api"

  source_configuration {
    auto_deployments_enabled = true

    authentication_configuration {
      connection_arn = var.apprunner_connection_arn
    }

    code_repository {
      repository_url   = var.github_repo_url
      source_directory = "backend"

      source_code_version {
        type  = "BRANCH"
        value = var.app_branch
      }

      code_configuration {
        # Build/run + env defined here (not apprunner.yaml) so secrets inject cleanly.
        configuration_source = "API"

        code_configuration_values {
          runtime       = "PYTHON_3"
          build_command = "pip install ."
          start_command = "uvicorn app.main:app --host 0.0.0.0 --port 8080"
          port          = "8080"

          runtime_environment_variables = {
            APP_ENV              = "production"
            AWS_REGION           = "us-east-1"
            S3_BUCKET_NAME       = aws_s3_bucket.documents.bucket
            KMS_KEY_ALIAS        = aws_kms_alias.heimdall.name
            COGNITO_USER_POOL_ID = aws_cognito_user_pool.heimdall.id
            COGNITO_CLIENT_ID    = aws_cognito_user_pool_client.heimdall.id
            COGNITO_REGION       = "us-east-1"
            BEDROCK_MODEL_ID     = var.bedrock_model_id
            FRONTEND_URL         = var.frontend_url
            LOG_LEVEL            = "INFO"
          }

          runtime_environment_secrets = {
            DATABASE_URL = aws_secretsmanager_secret.database_url.arn
          }
        }
      }
    }
  }

  instance_configuration {
    cpu               = "1024"
    memory            = "2048"
    instance_role_arn = aws_iam_role.app.arn # reuses the app role (Bedrock/S3/KMS/Secrets)
  }

  health_check_configuration {
    protocol = "HTTP"
    path     = "/healthz"
  }
}

output "apprunner_service_url" {
  description = "Public HTTPS URL of the backend API — set this as NEXT_PUBLIC_API_BASE_URL in Vercel."
  value       = "https://${aws_apprunner_service.backend.service_url}"
}
