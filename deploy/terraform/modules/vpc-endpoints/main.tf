terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

data "aws_region" "current" {}

# S3 gateway endpoint: always on, free, and required for ECR image layer pulls from private subnets.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${data.aws_region.current.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.private_route_table_ids

  tags = {
    Name = "${var.name}-s3"
  }
}

# Interface endpoints are billed per endpoint per AZ per hour, so they are off by default.
# The security group admits HTTPS from inside the VPC only and has no egress block:
# security groups are stateful, so replies to admitted requests still flow.
resource "aws_security_group" "vpce" {
  count = var.enable_interface_endpoints ? 1 : 0

  name        = "${var.name}-vpce"
  description = "HTTPS from inside the VPC to interface VPC endpoints"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTPS from the VPC CIDR"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr_block]
  }

  tags = {
    Name = "${var.name}-vpce"
  }
}

resource "aws_vpc_endpoint" "interface" {
  for_each = var.enable_interface_endpoints ? var.interface_services : toset([])

  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${data.aws_region.current.region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.vpce[0].id]

  tags = {
    Name = "${var.name}-${each.value}"
  }
}
