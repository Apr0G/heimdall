terraform {
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.0" }
    random = { source = "hashicorp/random", version = "~> 3.0" }
  }
}

provider "aws" {
  region = "us-east-1"
}

# --- variables ---
variable "db_password" {
  description = "Master password for the Postgres database"
  type        = string
  sensitive   = true
}

# random suffix so the S3 bucket name is globally unique
resource "random_id" "suffix" {
  byte_length = 4
}

# --- KMS: the encryption key for everything ---
resource "aws_kms_key" "heimdall" {
  description             = "Heimdall master encryption key"
  enable_key_rotation     = true
  deletion_window_in_days = 7
}

resource "aws_kms_alias" "heimdall" {
  name          = "alias/heimdall"
  target_key_id = aws_kms_key.heimdall.key_id
}

# --- S3: encrypted, private bucket for uploaded documents ---
resource "aws_s3_bucket" "documents" {
  bucket = "heimdall-documents-${random_id.suffix.hex}"
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.heimdall.arn
    }
  }
}

# CORS: the browser uploads documents directly to S3 via presigned URLs, so both
# the local dev origin and the deployed frontend (var.frontend_url) must be allowed.
resource "aws_s3_bucket_cors_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  cors_rule {
    allowed_methods = ["PUT", "GET", "HEAD"]
    allowed_origins = distinct(["http://localhost:3000", var.frontend_url])
    allowed_headers = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# --- RDS: encrypted Postgres database ---
resource "aws_db_instance" "heimdall" {
  identifier             = "heimdall-db"
  engine                 = "postgres"
  instance_class         = "db.t4g.micro" # smallest / cheapest
  allocated_storage      = 20
  db_name                = "heimdall"
  username               = "heimdall_admin"
  password               = var.db_password
  storage_encrypted      = true
  kms_key_id             = aws_kms_key.heimdall.arn
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = !var.rds_private # Phase gate (see rds-private.tf)
  apply_immediately      = true

  # PHI-readiness, flipped on together via rds_production (see rds-hardening.tf).
  # Default (false) keeps today's behavior so applying changes nothing.
  skip_final_snapshot        = !var.rds_production
  final_snapshot_identifier  = "heimdall-db-final"
  backup_retention_period    = var.rds_production ? 30 : 0
  deletion_protection        = var.rds_production
  copy_tags_to_snapshot      = true
  auto_minor_version_upgrade = true
  parameter_group_name       = var.rds_production ? aws_db_parameter_group.heimdall.name : null
}

# --- Cognito: user login for your app ---
resource "aws_cognito_user_pool" "heimdall" {
  name                     = "heimdall-users"
  mfa_configuration        = "OPTIONAL"
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }

  software_token_mfa_configuration { enabled = true }

  # Login-only product: no self-service signup. Only admins create users, so a
  # stranger can't register and get auto-provisioned into a practice.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }
}

resource "aws_cognito_user_pool_client" "heimdall" {
  name         = "heimdall-app-client"
  user_pool_id = aws_cognito_user_pool.heimdall.id

  # Backend brokers login via Cognito InitiateAuth (USER_PASSWORD_AUTH); refresh
  # for token renewal. Required for Phase 3 login to work.
  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]
}

# --- IAM: the role your app will use to call Bedrock + S3 ---
resource "aws_iam_role" "app" {
  name = "heimdall-app-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" } # ECS task role (used by Express)
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "app" {
  name = "heimdall-app-policy"
  role = aws_iam_role.app.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        # Scoped to Anthropic Claude models + their inference profiles.
        Resource = [
          "arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
          "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/us.anthropic.claude-*",
        ]
      },
      {
        Effect = "Allow"
        # Async Textract jobs do not support resource-level permissions.
        Action   = ["textract:StartDocumentTextDetection", "textract:GetDocumentTextDetection"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        # Scoped to the exact prefixes the app writes (see services/s3.py).
        Resource = [
          "${aws_s3_bucket.documents.arn}/tmp-uploads/*",
          "${aws_s3_bucket.documents.arn}/practices/*",
          "${aws_s3_bucket.documents.arn}/model_runs/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:GenerateDataKey"]
        Resource = aws_kms_key.heimdall.arn
      },
      {
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = [
          aws_secretsmanager_secret.db.arn,
          aws_secretsmanager_secret.database_url.arn,
        ]
      },
      {
        Effect   = "Allow"
        Action   = "sns:Publish"
        Resource = aws_sns_topic.leads.arn
      }
    ]
  })
}

# --- outputs: useful values printed after apply ---
output "s3_bucket_name" { value = aws_s3_bucket.documents.bucket }
output "db_endpoint" { value = aws_db_instance.heimdall.endpoint }
output "cognito_pool_id" { value = aws_cognito_user_pool.heimdall.id }
output "cognito_client_id" { value = aws_cognito_user_pool_client.heimdall.id }