# =============================================================================
# Per-practice PHI disposal (BAA offboarding). Runs app/scripts/dispose_practice.py
# as a one-off in-VPC ECS task. Isolated task + roles so the ability to permanently
# delete versioned PHI lives ONLY in this deliberately-invoked task, never in the
# always-on app role. DB creds are the LIMITED heimdall_app role, so disposal can
# delete case data but cannot touch audit_logs.
# =============================================================================

resource "aws_cloudwatch_log_group" "dispose" {
  name              = "/aws/ecs/heimdall-dispose"
  retention_in_days = 90
}

# Execution role: pull image + inject the app DB secret + write logs.
resource "aws_iam_role" "dispose_exec" {
  name = "heimdall-dispose-exec"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "dispose_exec" {
  name = "heimdall-dispose-exec"
  role = aws_iam_role.dispose_exec.id
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
      { Sid = "Logs", Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.dispose.arn}:*" },
      {
        Sid      = "Secret"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue", "kms:Decrypt"]
        Resource = [aws_secretsmanager_secret.app_database_url.arn, aws_kms_key.heimdall.arn]
      },
    ]
  })
}

# Task role: S3 list+delete of object VERSIONS on the documents bucket (true
# destruction on a versioned bucket), plus KMS to read encrypted objects.
resource "aws_iam_role" "dispose_task" {
  name = "heimdall-dispose-task"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "dispose_task" {
  name = "heimdall-dispose-task"
  role = aws_iam_role.dispose_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "ListVersions", Effect = "Allow", Action = ["s3:ListBucket", "s3:ListBucketVersions"], Resource = aws_s3_bucket.documents.arn },
      {
        Sid      = "DeleteVersions"
        Effect   = "Allow"
        Action   = ["s3:DeleteObject", "s3:DeleteObjectVersion"]
        Resource = "${aws_s3_bucket.documents.arn}/*"
      },
      { Sid = "Kms", Effect = "Allow", Action = ["kms:Decrypt", "kms:GenerateDataKey"], Resource = aws_kms_key.heimdall.arn },
    ]
  })
}

resource "aws_ecs_task_definition" "dispose" {
  family                   = "heimdall-dispose"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.dispose_exec.arn
  task_role_arn            = aws_iam_role.dispose_task.arn

  container_definitions = jsonencode([{
    name      = "dispose"
    image     = "${aws_ecr_repository.backend.repository_url}:latest"
    essential = true
    command   = ["python", "-m", "app.scripts.dispose_practice"]
    environment = [
      { name = "AWS_REGION", value = "us-east-1" },
      { name = "APP_ENV", value = "production" },
      { name = "S3_BUCKET_NAME", value = aws_s3_bucket.documents.bucket },
    ]
    secrets = [
      # heimdall_app (limited) — can delete case data, cannot touch audit_logs.
      { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.app_database_url.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.dispose.name
        "awslogs-region"        = "us-east-1"
        "awslogs-stream-prefix" = "dispose"
      }
    }
  }])
}
