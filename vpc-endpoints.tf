# =============================================================================
# VPC endpoints (PrivateLink) — keep AWS service traffic on the private AWS
# network instead of the public internet.
#
# - S3 gateway endpoint: FREE, always on (S3 holds the uploaded documents = PHI).
# - Interface endpoints (Bedrock, Textract, Secrets, KMS, Logs, ECR, STS): these
#   carry PHI (Bedrock/Textract) or credentials, but cost ~$0.01/hr per AZ each
#   (~$100/mo for the set). Off by default — set enable_interface_endpoints=true
#   to turn them on.
# =============================================================================

variable "enable_interface_endpoints" {
  description = "true = create interface VPC endpoints for Bedrock/Textract/Secrets/KMS/Logs/ECR/STS (~$100/mo). S3 gateway is always on and free."
  type        = bool
  default     = false
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_route_tables" "default" {
  vpc_id = data.aws_vpc.default.id
}

# --- S3 gateway endpoint (free) ----------------------------------------------
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = data.aws_vpc.default.id
  service_name      = "com.amazonaws.us-east-1.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = data.aws_route_tables.default.ids
}

# --- Interface endpoints (opt-in) --------------------------------------------
resource "aws_security_group" "vpce" {
  name        = "heimdall-vpce"
  description = "HTTPS from the VPC to interface endpoints"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTPS from within the VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.default.cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

locals {
  interface_services = [
    "bedrock-runtime", "textract", "secretsmanager",
    "kms", "logs", "ecr.api", "ecr.dkr", "sts",
  ]
}

resource "aws_vpc_endpoint" "interface" {
  for_each = var.enable_interface_endpoints ? toset(local.interface_services) : []

  vpc_id              = data.aws_vpc.default.id
  service_name        = "com.amazonaws.us-east-1.${each.key}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = slice(data.aws_subnets.default.ids, 0, 2) # 2 AZs for HA, keeps cost down
  security_group_ids  = [aws_security_group.vpce.id]
  private_dns_enabled = true
}
