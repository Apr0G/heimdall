# =============================================================================
# Remote Terraform state — an encrypted, versioned S3 bucket so your state (which
# contains the DB password and other secrets) lives in AWS, not as a file on your
# laptop. Uses S3-native locking (Terraform >= 1.11), so no DynamoDB needed.
#
# Two steps for you (documented in HIPAA-READINESS.md):
#   1. terraform apply                       # creates the bucket (state still local)
#   2. uncomment the backend block below, then:  terraform init -migrate-state
# =============================================================================

resource "aws_s3_bucket" "tfstate" {
  bucket = "heimdall-tfstate-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.heimdall.arn
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Same posture as the documents bucket (security.tf). The state file carries
# every secret Terraform has ever generated — the RDS master password, the
# heimdall_app password, the PHI hash pepper, the Redis AUTH token — and with
# versioning on, each ROTATED value would otherwise sit in an old version
# forever, so a rotation never actually retired the credential.
resource "aws_s3_bucket_policy" "tfstate_tls_only" {
  bucket = aws_s3_bucket.tfstate.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        aws_s3_bucket.tfstate.arn,
        "${aws_s3_bucket.tfstate.arn}/*",
      ]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

resource "aws_s3_bucket_lifecycle_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    id     = "expire-noncurrent-state"
    status = "Enabled"
    filter {}
    # 90 days is enough history to unwind a bad apply, and bounds how long a
    # rotated credential survives. The current version is never touched.
    noncurrent_version_expiration { noncurrent_days = 90 }
  }
}

# State now lives in the encrypted S3 bucket above. To activate/migrate, run:
#   terraform init -migrate-state
terraform {
  backend "s3" {
    bucket       = "heimdall-tfstate-000000000000"
    key          = "heimdall/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
