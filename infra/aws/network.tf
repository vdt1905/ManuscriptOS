# Network: a small dedicated VPC with one public subnet. All of these
# resources are free; there is no NAT gateway (that costs ~$32/month).

data "aws_availability_zones" "available" {
  state = "available"
}

# Trivy exception AWS-0178: VPC Flow Logs are stored in CloudWatch Logs, which
# is billed per GB; the only inbound path (CloudFront) has its own metrics.
#trivy:ignore:AWS-0178
resource "aws_vpc" "this" {
  cidr_block           = "10.20.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "docling-vpc" }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = { Name = "docling-igw" }
}

resource "aws_subnet" "public" {
  vpc_id            = aws_vpc.this.id
  cidr_block        = "10.20.1.0/24"
  availability_zone = data.aws_availability_zones.available.names[0]
  # No automatic public IPs: the server gets one fixed Elastic IP instead.
  map_public_ip_on_launch = false
  tags                    = { Name = "docling-public" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = { Name = "docling-public" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# ── Firewall ────────────────────────────────────────────────────────────────
# Inbound: ONLY CloudFront may reach the two API ports. No SSH (port 22) at
# all: shell access is through AWS Systems Manager Session Manager instead.

data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_security_group" "app" {
  name        = "docling-app"
  description = "Docling API server: reachable only from CloudFront"
  vpc_id      = aws_vpc.this.id
}

resource "aws_vpc_security_group_ingress_rule" "from_cloudfront" {
  security_group_id = aws_security_group.app.id
  description       = "ai-service (8000) and auth-service (8001), from CloudFront only"
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront.id
  ip_protocol       = "tcp"
  from_port         = 8000
  to_port           = 8001
}

# Outbound: only HTTPS and MongoDB. The destinations (container registry,
# Groq API, MongoDB Atlas, AWS APIs) have changing IP addresses, so the rules
# cannot be narrowed to fixed addresses (hence the Trivy exception).
#trivy:ignore:AWS-0104
resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.app.id
  description       = "HTTPS: container registry, Groq API, AWS APIs, LaTeX packages"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

#trivy:ignore:AWS-0104
resource "aws_vpc_security_group_egress_rule" "mongodb" {
  security_group_id = aws_security_group.app.id
  description       = "MongoDB Atlas"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 27017
  to_port           = 27017
}
