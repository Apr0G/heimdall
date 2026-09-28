# =============================================================================
# Security hardening — ADDITIVE infrastructure. Review `terraform plan` before
# `apply`. Nothing here mutates existing resources destructively.
#
# The RISKY cutovers are intentionally NOT here (they break connectivity and
# need a coordinated apply): making RDS private + force_ssl + SG lockdown,
# requiring Cognito MFA + shorter token TTLs, migrating the app to read the DB
# secret at runtime, and moving Terraform state to an encrypted S3 backend.
# Those are documented as exact diffs in SECURITY.md.
# =============================================================================

data "aws_caller_identity" "current" {}

data "aws_vpc" "default" {
  default = true
}

# --- S3: deny non-TLS access + expire temp uploads ---------------------------
resource "aws_s3_bucket_policy" "documents_tls_only" {
  bucket = aws_s3_bucket.documents.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.documents.arn,
        "${aws_s3_bucket.documents.arn}/*",
      ]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    id     = "expire-temp-uploads"
    status = "Enabled"
    filter { prefix = "tmp-uploads/" }
    expiration { days = 1 }
    # Bucket is versioned: also purge noncurrent versions so the transient PHI
    # upload is actually deleted, not just hidden behind a delete marker.
    noncurrent_version_expiration { noncurrent_days = 1 }
  }

  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }

  # The corpus export writes to exports/quarantine/<export_id>/ — STILL PHI until
  # a reviewer promotes it (scripts/promote_corpus.py -> exports/released/, no
  # lifecycle). A corpus nobody reviews must not sit there forever: 30 days, then
  # gone, noncurrent versions with it. exports/released/ holds only data that
  # meets 45 CFR 164.514(b)(2) and is the permanent training store.
  rule {
    id     = "expire-corpus-quarantine"
    status = "Enabled"
    filter { prefix = "exports/quarantine/" }
    expiration { days = 30 }
    noncurrent_version_expiration { noncurrent_days = 1 }
  }

  # Raw Bedrock request/response archives (model_runs/) contain full document text
  # (PHI) + raw member IDs. Strategy: keep them only long enough to debug/reprocess,
  # then delete. The DE-IDENTIFIED corpus (exports/released/) is the permanent
  # training store and is reproducible from the DB, so raw PHI is NOT kept forever.
  # Set model_runs_retention_days = 0 to keep indefinitely (not advised).
  dynamic "rule" {
    for_each = var.model_runs_retention_days > 0 ? [1] : []
    content {
      id     = "expire-model-run-archives"
      status = "Enabled"
      filter { prefix = "model_runs/" }
      expiration { days = var.model_runs_retention_days }
      # Versioned bucket: purge noncurrent versions too, so the PHI is truly gone.
      noncurrent_version_expiration { noncurrent_days = 1 }
    }
  }
}

variable "model_runs_retention_days" {
  description = "Days to keep raw model_runs/ PHI archives before deletion. The de-identified corpus (exports/released/) is the permanent training store. 0 = keep indefinitely (not advised)."
  type        = number
  default     = 30
}

# --- GuardDuty ----------------------------------------------------------------
resource "aws_guardduty_detector" "main" {
  enable = true
}

# Route GuardDuty findings (sev >= 4 = medium/high) to the alerts topic —
# otherwise a credential-exfil or crypto-mining finding sits unseen in the
# console. For a one-person op, unrouted detection is close to no detection.
resource "aws_cloudwatch_event_rule" "guardduty_findings" {
  name        = "heimdall-guardduty-findings"
  description = "GuardDuty medium/high findings -> alerts SNS"
  event_pattern = jsonencode({
    source      = ["aws.guardduty"]
    detail-type = ["GuardDuty Finding"]
    detail      = { severity = [{ numeric = [">=", 4] }] }
  })
}

resource "aws_cloudwatch_event_target" "guardduty_to_sns" {
  rule      = aws_cloudwatch_event_rule.guardduty_findings.name
  target_id = "alerts"
  arn       = aws_sns_topic.alerts.arn
}

# Access policy for the (KMS-encrypted) alerts topic. An aws_sns_topic_policy
# REPLACES the topic's default policy wholesale — it does not add to it — so
# every service that publishes here must be listed explicitly. The 2026-08-25
# version carried only the EventBridge statement, which silently cut off every
# CloudWatch alarm (root usage, unauthorized calls, IAM changes, RDS, Lambda
# errors) and every SES bounce/complaint: the alarm history read "Failed to
# execute action" for three days and nobody was emailed. The KMS key's
# AllowSnsPublishers statement (main.tf) lists the same three services.
resource "aws_sns_topic_policy" "alerts_events" {
  arn = aws_sns_topic.alerts.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowEventBridgePublish"
        Effect    = "Allow"
        Principal = { Service = "events.amazonaws.com" }
        Action    = "sns:Publish"
        Resource  = aws_sns_topic.alerts.arn
        Condition = {
          ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.guardduty_findings.arn }
        }
      },
      {
        # CloudWatch alarm actions (monitoring.tf, cognito-email-sender.tf).
        # Confused-deputy guard: the service principal is shared across all of
        # AWS, so pin it to alarms owned by THIS account.
        Sid       = "AllowCloudWatchAlarmsPublish"
        Effect    = "Allow"
        Principal = { Service = "cloudwatch.amazonaws.com" }
        Action    = "sns:Publish"
        Resource  = aws_sns_topic.alerts.arn
        Condition = {
          StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
        }
      },
      {
        # SES bounce / complaint notifications for the sending domain (ses.tf).
        Sid       = "AllowSesNotificationsPublish"
        Effect    = "Allow"
        Principal = { Service = "ses.amazonaws.com" }
        Action    = "sns:Publish"
        Resource  = aws_sns_topic.alerts.arn
        Condition = {
          StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
        }
      },
    ]
  })
}

# --- CloudTrail (all regions + log-file validation) + Object-Lock audit bucket -
resource "aws_s3_bucket" "trail" {
  bucket              = "heimdall-cloudtrail-${random_id.suffix.hex}"
  object_lock_enabled = true
}

resource "aws_s3_bucket_public_access_block" "trail" {
  bucket                  = aws_s3_bucket.trail.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "trail" {
  bucket = aws_s3_bucket.trail.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "trail" {
  bucket = aws_s3_bucket.trail.id
  rule {
    apply_server_side_encryption_by_default {
      # SSE-S3 (not the CMK) so CloudTrail can write without a KMS key-policy
      # grant. Still encrypted at rest. To upgrade to the customer key later,
      # add a CloudTrail grant to the key policy first (see SECURITY.md).
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_object_lock_configuration" "trail" {
  bucket     = aws_s3_bucket.trail.id
  depends_on = [aws_s3_bucket_versioning.trail]
  rule {
    default_retention {
      mode = "GOVERNANCE"
      days = 2555 # ~7 years for HIPAA — confirm exact retention (see SECURITY.md)
    }
  }
}

resource "aws_s3_bucket_policy" "trail" {
  bucket = aws_s3_bucket.trail.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AWSCloudTrailAclCheck"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:GetBucketAcl"
        Resource  = aws_s3_bucket.trail.arn
      },
      {
        Sid       = "AWSCloudTrailWrite"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.trail.arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*"
        Condition = { StringEquals = { "s3:x-amz-acl" = "bucket-owner-full-control" } }
      },
    ]
  })
}

resource "aws_cloudtrail" "main" {
  name                          = "heimdall-trail"
  s3_bucket_name                = aws_s3_bucket.trail.id
  is_multi_region_trail         = true
  include_global_service_events = true
  enable_log_file_validation    = true
  # Also stream to CloudWatch Logs so the security metric-filter alarms fire
  # (see monitoring.tf). Kept optional-safe: both refs live in monitoring.tf.
  cloud_watch_logs_group_arn = "${aws_cloudwatch_log_group.cloudtrail.arn}:*"
  cloud_watch_logs_role_arn  = aws_iam_role.cloudtrail_cw.arn
  depends_on                 = [aws_s3_bucket_policy.trail]

  # Preserve management-event logging (advanced selectors replace the default).
  advanced_event_selector {
    name = "Management events"
    field_selector {
      field  = "eventCategory"
      equals = ["Management"]
    }
  }

  # S3 object-level (data) events on the PHI documents bucket, so presigned-URL
  # GET/PUT — which happen OUTSIDE the app — are logged. If a presigned URL leaks
  # inside its 15-min window, its use is now recorded. Adds S3 data-event charges
  # (~$0.10 per 100k events); scoped to two buckets to keep cost/volume down.
  # The Terraform state bucket is the second: its objects hold every generated
  # secret, so a read of the state from anything other than a plan/apply is
  # exactly the access that should leave a trail (backend-state.tf).
  advanced_event_selector {
    name = "S3 data events (documents + tfstate buckets)"
    field_selector {
      field  = "eventCategory"
      equals = ["Data"]
    }
    field_selector {
      field  = "resources.type"
      equals = ["AWS::S3::Object"]
    }
    field_selector {
      field       = "resources.ARN"
      starts_with = ["${aws_s3_bucket.documents.arn}/", "${aws_s3_bucket.tfstate.arn}/"]
    }
  }
}

# --- VPC Flow Logs on the default VPC ----------------------------------------
resource "aws_cloudwatch_log_group" "flow" {
  name              = "/heimdall/vpc-flow-logs"
  retention_in_days = 90
  kms_key_id        = aws_kms_key.heimdall.arn
}

resource "aws_iam_role" "flow" {
  name = "heimdall-flow-logs-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "vpc-flow-logs.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "flow" {
  name = "heimdall-flow-logs-policy"
  role = aws_iam_role.flow.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams",
      ]
      Resource = "${aws_cloudwatch_log_group.flow.arn}:*"
    }]
  })
}

resource "aws_flow_log" "default" {
  iam_role_arn    = aws_iam_role.flow.arn
  log_destination = aws_cloudwatch_log_group.flow.arn
  traffic_type    = "ALL"
  vpc_id          = data.aws_vpc.default.id
}

# --- Secrets Manager: DB credential (scaffolding) ----------------------------
# Creates the secret so the app can read the DB credential at runtime (Phase 6
# app change, done under coordination). Value mirrors the current RDS master.
resource "aws_secretsmanager_secret" "db" {
  name        = "heimdall/db"
  description = "Heimdall database credentials"
  kms_key_id  = aws_kms_key.heimdall.arn
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    username = aws_db_instance.heimdall.username
    password = var.db_password
    host     = aws_db_instance.heimdall.address
    port     = 5432
    dbname   = aws_db_instance.heimdall.db_name
  })
}

