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

  # Raw Bedrock request/response archives (model_runs/) contain full document text
  # (PHI) + raw member IDs. Strategy: keep them only long enough to debug/reprocess,
  # then delete. The DE-IDENTIFIED corpus (scripts/export_corpus.py -> exports/) is
  # the permanent training store and is reproducible from the DB, so raw PHI is NOT
  # kept forever. Set model_runs_retention_days = 0 to keep indefinitely (not advised).
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
  description = "Days to keep raw model_runs/ PHI archives before deletion. The de-identified corpus (exports/) is the permanent training store. 0 = keep indefinitely (not advised)."
  type        = number
  default     = 30
}

# --- GuardDuty ----------------------------------------------------------------
resource "aws_guardduty_detector" "main" {
  enable = true
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
  # (~$0.10 per 100k events); scoped to the one bucket to keep cost/volume down.
  advanced_event_selector {
    name = "S3 data events (documents bucket)"
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
      starts_with = ["${aws_s3_bucket.documents.arn}/"]
    }
  }
}

# --- VPC Flow Logs on the default VPC ----------------------------------------
resource "aws_cloudwatch_log_group" "flow" {
  name              = "/heimdall/vpc-flow-logs"
  retention_in_days = 90
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

# --- WAFv2 web ACL (COUNT mode) — ready to associate with CloudFront ----------
# Managed rules run in COUNT so nothing is blocked yet. Review CloudWatch
# metrics, then switch override_action to `none {}` + add CloudFront + associate
# in a follow-up (Phase 2). CLOUDFRONT scope must live in us-east-1 (it does).
resource "aws_wafv2_web_acl" "cloudfront" {
  name        = "heimdall-waf"
  description = "Heimdall edge WAF - count mode until reviewed"
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "heimdall-waf"
    sampled_requests_enabled   = true
  }

  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1
    override_action {
      count {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesCommonRuleSet"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "common"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 2
    override_action {
      count {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "RateLimitPerIp"
    priority = 3
    action {
      count {}
    }
    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "rate-limit"
      sampled_requests_enabled   = true
    }
  }
}
