# =============================================================================
# De-identified corpus export + release (HIPAA Safe Harbor, 45 CFR 164.514(b)(2)).
#
# app/scripts/export_corpus.py and app/scripts/promote_corpus.py run as one-off
# in-VPC ECS tasks on the `deid` image stage (Presidio + clinical transformer +
# torch baked in, hub offline). Isolated task definition + roles so:
#   - the always-on API task never carries Comprehend Medical or exports/ write
#     access, and
#   - the export task carries nothing but what it needs: read the model_runs/
#     archive (raw member id for exact-match redaction), read/write exports/,
#     DetectPHI, and the LIMITED heimdall_app DB role (INSERT on the corpus
#     tables and audit_logs; cannot touch anything else).
#
# Amazon Comprehend Medical: HIPAA-eligible, excluded from AWS's service-
# improvement clause (Service Terms §50.3), reached over PrivateLink with an
# endpoint policy that allows DetectPHI and nothing else.
# =============================================================================

variable "deid_permitted_baa_versions" {
  description = "Comma-separated customer BAA versions whose text permits Heimdall to create de-identified data (45 CFR 164.502(d)(1)). EMPTY = the export refuses to run. Set only after the BAA clause exists."
  type        = string
  default     = ""
}

variable "enable_comprehend_endpoint" {
  description = "Interface VPC endpoint for Comprehend Medical (~$0.01/hr per AZ, two AZs). true keeps DetectPHI traffic on PrivateLink; false sends it over TLS to the public AWS endpoint."
  type        = bool
  default     = true
}

# --- PrivateLink to Comprehend Medical, DetectPHI only ------------------------
resource "aws_vpc_endpoint" "comprehendmedical" {
  count = var.enable_comprehend_endpoint ? 1 : 0

  vpc_id              = data.aws_vpc.default.id
  service_name        = "com.amazonaws.us-east-1.comprehendmedical"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = slice(data.aws_subnets.default.ids, 0, 2)
  security_group_ids  = [aws_security_group.vpce.id]
  private_dns_enabled = true

  # The endpoint policy is a second gate independent of IAM: even a principal
  # holding comprehendmedical:* can only call DetectPHI through this endpoint.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = ["comprehendmedical:DetectPHI"]
      Resource  = "*"
    }]
  })

  tags = { Name = "heimdall-vpce-comprehendmedical" }
}

# --- Logs --------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "deid" {
  name              = "/aws/ecs/heimdall-deid"
  retention_in_days = 90
  kms_key_id        = aws_kms_key.heimdall.arn
}

# --- Execution role: pull the :deid image, inject the app DB secret, write logs ---
resource "aws_iam_role" "deid_exec" {
  name = "heimdall-deid-exec"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "deid_exec" {
  name = "heimdall-deid-exec"
  role = aws_iam_role.deid_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "EcrAuth", Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
      {
        Sid      = "EcrImage"
        Effect   = "Allow"
        Action   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
        Resource = aws_ecr_repository.backend.arn
      },
      { Sid = "Logs", Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.deid.arn}:*" },
      {
        Sid      = "Secret"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue", "kms:Decrypt"]
        Resource = [aws_secretsmanager_secret.app_database_url.arn, aws_kms_key.heimdall.arn]
      },
    ]
  })
}

# --- Task role: exactly the export's and promote's needs ---------------------------
resource "aws_iam_role" "deid_task" {
  name = "heimdall-deid-task"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "deid_task" {
  name = "heimdall-deid-task"
  role = aws_iam_role.deid_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Raw member id for exact-match redaction lives only in the extraction
        # call's archived response (30-day lifecycle). Read-only.
        Sid      = "ReadModelRunArchive"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.documents.arn}/model_runs/*"
      },
      {
        # Quarantine write + read-back; released write. No delete: a corpus
        # leaves quarantine by lifecycle expiry or by promotion, never by hand.
        Sid      = "CorpusPrefixes"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${aws_s3_bucket.documents.arn}/exports/*"
      },
      { Sid = "Kms", Effect = "Allow", Action = ["kms:Decrypt", "kms:GenerateDataKey"], Resource = aws_kms_key.heimdall.arn },
      {
        # Detector A. DetectPHI has no resource-level scoping; the endpoint
        # policy above narrows the action set a second time.
        Sid      = "ComprehendMedicalDetectPhi"
        Effect   = "Allow"
        Action   = ["comprehendmedical:DetectPHI"]
        Resource = "*"
      },
    ]
  })
}

# --- Task definition ------------------------------------------------------------------
resource "aws_ecs_task_definition" "deid" {
  family                   = "heimdall-deid"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  # The transformer runs on CPU: 2 vCPU keeps a few-hundred-letter corpus to
  # minutes; 8 GB leaves headroom for torch + the model + the loaded rows.
  cpu                = "2048"
  memory             = "8192"
  execution_role_arn = aws_iam_role.deid_exec.arn
  task_role_arn      = aws_iam_role.deid_task.arn

  container_definitions = jsonencode([{
    name      = "deid"
    image     = "${aws_ecr_repository.backend.repository_url}:deid"
    essential = true
    # export by default; promote-corpus.yml overrides the command.
    command = ["python", "-m", "app.scripts.export_corpus"]
    environment = [
      { name = "AWS_REGION", value = "us-east-1" },
      { name = "APP_ENV", value = "production" },
      { name = "S3_BUCKET_NAME", value = aws_s3_bucket.documents.bucket },
      { name = "DB_SSL_CA_BUNDLE", value = "/app/rds-ca.pem" },
      { name = "DEID_NLP_ENGINE", value = "transformers" },
      { name = "DEID_MODEL_MANIFEST", value = "/app/deid-model.json" },
      { name = "DEID_PERMITTED_BAA_VERSIONS", value = var.deid_permitted_baa_versions },
      { name = "HF_HOME", value = "/app/hf" },
      { name = "HF_HUB_OFFLINE", value = "1" },
      { name = "TRANSFORMERS_OFFLINE", value = "1" },
    ]
    secrets = [
      # heimdall_app (limited): SELECT on the case family, INSERT on the corpus
      # tables + audit_logs. No pepper — the export hashes nothing.
      { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.app_database_url.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.deid.name
        "awslogs-region"        = "us-east-1"
        "awslogs-stream-prefix" = "deid"
      }
    }
  }])
}
