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

  # An explicit policy is REQUIRED for the CloudWatch Logs statement below: with
  # the default key policy, attaching `kms_key_id` to a log group fails outright
  # because the logs service principal cannot use the key. The log groups carry
  # request paths, case UUIDs and exception text, so encrypting them at rest is
  # the point of the exercise.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Root retains full control. Without this the key becomes unmanageable —
        # KMS does not fall back to IAM when an explicit policy is present.
        Sid       = "EnableIAMUserPermissions"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "AllowCloudWatchLogs"
        Effect    = "Allow"
        Principal = { Service = "logs.us-east-1.amazonaws.com" }
        Action = [
          "kms:Encrypt*",
          "kms:Decrypt*",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:Describe*",
        ]
        Resource = "*"
        # Scope to this account's log groups so the key cannot be used by another
        # account's logs even if the service principal is shared.
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:us-east-1:${data.aws_caller_identity.current.account_id}:log-group:*"
          }
        }
      },
    ]
  })
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
variable "cognito_mfa" {
  description = "Cognito MFA mode. TOTP is REQUIRED (ON) — users without MFA enroll via QR on next login. The login+enrollment flow is verified in prod, so ON is the default; do not weaken to OPTIONAL/OFF for a PHI system."
  type        = string
  default     = "ON"
  validation {
    condition     = contains(["ON", "OPTIONAL", "OFF"], var.cognito_mfa)
    error_message = "cognito_mfa must be ON, OPTIONAL, or OFF."
  }
}

resource "aws_cognito_user_pool" "heimdall" {
  name                     = "heimdall-users"
  mfa_configuration        = var.cognito_mfa
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
    # Invites (temporary passwords) expire after this; re-run provision-user to
    # re-send. Explicit rather than the AWS default so the policy is in the repo.
    temporary_password_validity_days = 7
  }

  software_token_mfa_configuration { enabled = true }

  # Who the invite / reset-code emails come from. COGNITO_DEFAULT is AWS's
  # no-reply@verificationemail.com; DEVELOPER sends through our SES identity
  # (ses.tf) as no-reply@heimdallclaims.com. Gated — see ses.tf for why.
  email_configuration {
    email_sending_account  = var.cognito_email_from_ses ? "DEVELOPER" : "COGNITO_DEFAULT"
    source_arn             = var.cognito_email_from_ses ? aws_ses_domain_identity.heimdall.arn : null
    from_email_address     = var.cognito_email_from_ses ? local.mail_from : null
    reply_to_email_address = var.cognito_email_from_ses ? local.mail_reply_to : null
  }

  # Self-service "forgot password" goes through the verified email only — never
  # SMS/phone, which we don't collect.
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # The email carrying the forgot-password code ({####}).
  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_subject        = "Your Heimdall password reset code"
    email_message        = <<-EOT
      <p>Hello,</p>
      <p>Someone asked to reset the password for your Heimdall account. Enter this code on the reset screen:</p>
      <p style="font-size:20px;letter-spacing:4px"><strong>{####}</strong></p>
      <p>The code expires in one hour. If you didn't request this, you can ignore this email — your password hasn't changed.</p>
      <p>— Heimdall</p>
    EOT
  }

  # Login-only product: no self-service signup. Only admins create users, so a
  # stranger can't register and get auto-provisioned into a practice.
  admin_create_user_config {
    allow_admin_create_user_only = true

    # The invite a provisioned user receives. {username} / {####} are Cognito's
    # placeholders for the email and the temporary password. First login forces
    # them to choose their own password, then enroll an authenticator.
    invite_message_template {
      email_subject = "Your Heimdall account"
      email_message = <<-EOT
        <p>Hello,</p>
        <p>An account has been created for you on Heimdall, your practice's appeal-drafting workspace.</p>
        <p>Sign in at <a href="https://heimdallclaims.com/login">heimdallclaims.com/login</a> with:</p>
        <p>Email: {username}<br/>Temporary password: {####}</p>
        <p>You'll be asked to choose your own password and set up an authenticator app. This temporary password expires in 7 days — if it has, ask your administrator to send a new one.</p>
        <p>— Heimdall</p>
      EOT
      sms_message   = "Your Heimdall username is {username} and temporary password is {####}"
    }
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

  # Unknown users get the same error as a wrong password, and ForgotPassword for
  # an unknown address succeeds silently — so login/reset can't enumerate accounts.
  # The API also normalises these on its side; this closes the gap at the source.
  prevent_user_existence_errors = "ENABLED"
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
        # Cognito user administration, scoped to our pool:
        #  - /api/admin/users (require_role("admin"), audit row per call): invite,
        #    re-send invite, disable/enable, global sign-out.
        #  - authenticator recovery (/api/auth/mfa/recover/*): Cognito cannot drop
        #    a TOTP device while the pool requires MFA, so after the person proves
        #    password + emailed code the identity is recreated with the same
        #    password (AdminDeleteUser + AdminCreateUser + AdminSetUserPassword).
        #    Audited as mfa_reset; every session revoked.
        Sid    = "CognitoUserAdmin"
        Effect = "Allow"
        Action = [
          "cognito-idp:AdminCreateUser",
          "cognito-idp:AdminGetUser",
          "cognito-idp:AdminDisableUser",
          "cognito-idp:AdminEnableUser",
          "cognito-idp:AdminUserGlobalSignOut",
          "cognito-idp:AdminDeleteUser",
          "cognito-idp:AdminSetUserPassword",
        ]
        Resource = aws_cognito_user_pool.heimdall.arn
      },
      {
        # The API emails authenticator-recovery codes itself (services/mailer.py)
        # from no-reply@heimdallclaims.com. Limited to our verified identity.
        Sid      = "SesSendRecoveryCodes"
        Effect   = "Allow"
        Action   = ["ses:SendEmail", "ses:SendRawEmail"]
        Resource = aws_ses_domain_identity.heimdall.arn
        # ses:FromAddress carries the full header value, display name included
        # ("Heimdall <no-reply@...>"), so match both bare and named forms.
        Condition = {
          StringLike = {
            "ses:FromAddress" = ["no-reply@heimdallclaims.com", "*<no-reply@heimdallclaims.com>"]
          }
        }
      },
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
        # exports/ holds the training-corpus JSONL (scripts/export_corpus.py).
        Resource = [
          "${aws_s3_bucket.documents.arn}/tmp-uploads/*",
          "${aws_s3_bucket.documents.arn}/practices/*",
          "${aws_s3_bucket.documents.arn}/model_runs/*",
          "${aws_s3_bucket.documents.arn}/exports/*",
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