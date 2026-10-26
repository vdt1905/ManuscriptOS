# The API server: one free-tier EC2 instance running the auth-service and
# ai-service containers with Docker Compose. The pipeline deploys to it
# through AWS Systems Manager, so no SSH key or open SSH port exists.

# Latest Amazon Linux 2023 (free-tier eligible; Docker and the SSM agent
# are available out of the box).
data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

# ── Permissions of the server itself ────────────────────────────────────────
resource "aws_iam_role" "server" {
  name = "docling-server"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Lets Systems Manager run the pipeline's deploy commands (and gives you a
# browser shell via Session Manager).
resource "aws_iam_role_policy_attachment" "server_ssm" {
  role       = aws_iam_role.server.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Read the app's secrets, and nothing else.
resource "aws_iam_role_policy" "server_secrets" {
  name = "read-docling-secrets"
  role = aws_iam_role.server.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["ssm:GetParametersByPath", "ssm:GetParameters"]
      Resource = [
        "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/docling",
        "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/docling/*",
      ]
    }]
  })
}

resource "aws_iam_instance_profile" "server" {
  name = "docling-server"
  role = aws_iam_role.server.name
}

data "aws_caller_identity" "current" {}

# ── The instance ────────────────────────────────────────────────────────────
resource "aws_instance" "server" {
  ami                    = data.aws_ssm_parameter.al2023.value
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.server.name
  user_data              = file("${path.module}/user_data.sh")

  # "standard" credits: when the CPU burst budget runs out the instance slows
  # down instead of AWS billing for extra CPU ("unlimited", the t3 default).
  credit_specification {
    cpu_credits = "standard"
  }

  # IMDSv2 only: blocks the classic SSRF trick of stealing the server's
  # AWS credentials through the metadata endpoint.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  # Encrypted with the AWS managed key (no extra cost).
  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.disk_gb
    encrypted             = true
    delete_on_termination = true
  }

  tags = { Name = "docling-server" }

  lifecycle {
    # A newer Amazon Linux image must not replace the running server.
    ignore_changes = [ami]
  }
}

# A fixed public address, so CloudFront's origin never changes. It is the
# only public IPv4 address in the stack (the instance gets no other one).
resource "aws_eip" "server" {
  domain     = "vpc"
  instance   = aws_instance.server.id
  depends_on = [aws_internet_gateway.this]
  tags       = { Name = "docling-server" }
}
