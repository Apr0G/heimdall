# =============================================================================
# User provisioning. Runs app/scripts/provision_user.py as a one-off in-VPC ECS
# task: creates the Cognito account (Cognito emails the temporary password) and
# the matching `users` row. This is the fallback path when no admin can sign in;
# the primary path is the in-app admin UI, whose task role (main.tf
# CognitoUserAdmin) holds the same AdminCreateUser plus the delete/set-password
# pair the authenticator-recovery flow needs. That grant is an accepted risk:
# Cognito IAM cannot scope admin actions per user, and the API gates every use
# behind require_role("admin") or the password + emailed-code proof.
# =============================================================================

resource "aws_cloudwatch_log_group" "provision" {
  name              = "/aws/ecs/heimdall-provision"
  retention_in_days = 90
  kms_key_id        = aws_kms_key.heimdall.arn
}

resource "aws_iam_role" "provision_exec" {
  name = "heimdall-provision-exec"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "provision_exec" {
  name = "heimdall-provision-exec"
  role = aws_iam_role.provision_exec.id
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
      { Sid = "Logs", Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.provision.arn}:*" },
      {
        Sid      = "Secret"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue", "kms:Decrypt"]
        Resource = [aws_secretsmanager_secret.app_database_url.arn, aws_kms_key.heimdall.arn]
      },
    ]
  })
}

resource "aws_iam_role" "provision_task" {
  name = "heimdall-provision-task"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "provision_task" {
  name = "heimdall-provision-task"
  role = aws_iam_role.provision_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "InviteUsers"
      Effect   = "Allow"
      Action   = ["cognito-idp:AdminCreateUser"]
      Resource = aws_cognito_user_pool.heimdall.arn
    }]
  })
}

resource "aws_ecs_task_definition" "provision" {
  family                   = "heimdall-provision"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.provision_exec.arn
  task_role_arn            = aws_iam_role.provision_task.arn

  container_definitions = jsonencode([{
    name      = "provision"
    image     = "${aws_ecr_repository.backend.repository_url}:latest"
    essential = true
    command   = ["python", "-m", "app.scripts.provision_user"]
    environment = [
      { name = "AWS_REGION", value = "us-east-1" },
      { name = "APP_ENV", value = "production" },
      { name = "COGNITO_USER_POOL_ID", value = aws_cognito_user_pool.heimdall.id },
      { name = "COGNITO_CLIENT_ID", value = aws_cognito_user_pool_client.heimdall.id },
    ]
    secrets = [
      { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.app_database_url.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.provision.name
        "awslogs-region"        = "us-east-1"
        "awslogs-stream-prefix" = "provision"
      }
    }
  }])
}
