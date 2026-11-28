# Offline tests: the mocked AWS provider needs no credentials and makes no AWS calls.
# Run with: terraform -chdir=deploy/terraform/modules/vpc init -backend=false && terraform -chdir=deploy/terraform/modules/vpc test

mock_provider "aws" {
  # Computed ARNs must look like ARNs, or the provider's own validation rejects the mock values.
  mock_resource "aws_cloudwatch_log_group" {
    defaults = {
      arn = "arn:aws:logs:us-east-1:111111111111:log-group:/vpc/test/flow-logs"
    }
  }

  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::111111111111:role/test-flow-logs"
    }
  }

  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "111111111111"
    }
  }
}

variables {
  name = "test"
  azs  = ["az-a", "az-b"]
}

run "defaults" {
  command = apply

  assert {
    condition     = aws_vpc.this.cidr_block == "10.40.0.0/16"
    error_message = "VPC must default to 10.40.0.0/16."
  }

  assert {
    condition     = aws_vpc.this.enable_dns_support && aws_vpc.this.enable_dns_hostnames
    error_message = "VPC must enable DNS support and DNS hostnames."
  }

  assert {
    condition     = [for s in aws_subnet.public : s.cidr_block] == ["10.40.0.0/24", "10.40.1.0/24"]
    error_message = "Public subnets must be 10.40.0.0/24 and 10.40.1.0/24."
  }

  assert {
    condition     = [for s in aws_subnet.private : s.cidr_block] == ["10.40.10.0/24", "10.40.11.0/24"]
    error_message = "Private subnets must be 10.40.10.0/24 and 10.40.11.0/24."
  }

  assert {
    condition     = [for s in aws_subnet.public : s.availability_zone] == ["az-a", "az-b"] && [for s in aws_subnet.private : s.availability_zone] == ["az-a", "az-b"]
    error_message = "Subnets must follow var.azs order."
  }

  assert {
    condition     = alltrue([for s in aws_subnet.public : s.map_public_ip_on_launch == false])
    error_message = "Public subnets must not auto-assign public IPs."
  }

  assert {
    condition     = aws_route.public_internet.destination_cidr_block == "0.0.0.0/0" && aws_route.public_internet.gateway_id == aws_internet_gateway.this.id
    error_message = "Public route table must send 0.0.0.0/0 to the internet gateway."
  }

  assert {
    condition     = length(aws_eip.nat) == 0 && length(aws_nat_gateway.this) == 0 && length(aws_route.private_nat) == 0
    error_message = "No EIP, NAT gateway or private default route by default."
  }

  assert {
    condition     = length(aws_default_security_group.this.ingress) == 0 && length(aws_default_security_group.this.egress) == 0
    error_message = "Default security group must have no rules."
  }

  assert {
    condition     = aws_cloudwatch_log_group.flow_logs[0].name == "/vpc/test/flow-logs" && aws_cloudwatch_log_group.flow_logs[0].retention_in_days == 7
    error_message = "Flow log group must be /vpc/test/flow-logs with 7-day retention."
  }

  assert {
    condition     = length(aws_flow_log.this) == 1 && aws_flow_log.this[0].traffic_type == "ALL" && aws_flow_log.this[0].vpc_id == aws_vpc.this.id
    error_message = "Flow log must capture ALL traffic for the VPC."
  }

  assert {
    condition     = jsondecode(aws_iam_role.flow_logs[0].assume_role_policy).Statement[0].Principal.Service == "vpc-flow-logs.amazonaws.com"
    error_message = "Only vpc-flow-logs.amazonaws.com may assume the flow logs role."
  }

  assert {
    condition     = jsondecode(aws_iam_role.flow_logs[0].assume_role_policy).Statement[0].Condition.StringEquals["aws:SourceAccount"] == data.aws_caller_identity.current.account_id
    error_message = "Flow logs trust policy must carry an aws:SourceAccount condition."
  }

  assert {
    condition = toset(jsondecode(aws_iam_role_policy.flow_logs[0].policy).Statement[0].Action) == toset([
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
    ])
    error_message = "Flow logs policy must allow only the four log actions."
  }

  assert {
    condition = jsondecode(aws_iam_role_policy.flow_logs[0].policy).Statement[0].Resource == [
      aws_cloudwatch_log_group.flow_logs[0].arn,
      "${aws_cloudwatch_log_group.flow_logs[0].arn}:*",
    ]
    error_message = "Flow logs policy must be scoped to the log group ARN and ARN:* only."
  }

  assert {
    condition     = output.public_subnet_ids == aws_subnet.public[*].id && output.private_subnet_ids == aws_subnet.private[*].id
    error_message = "Subnet id outputs must be in var.azs order."
  }

  assert {
    condition     = output.private_subnet_ids_by_az == { "az-a" = aws_subnet.private[0].id, "az-b" = aws_subnet.private[1].id }
    error_message = "private_subnet_ids_by_az must map each AZ to its private subnet."
  }

  assert {
    condition     = output.private_route_table_id == aws_route_table.private.id && output.vpc_id == aws_vpc.this.id && output.vpc_cidr_block == "10.40.0.0/16"
    error_message = "VPC and route table outputs must match the resources."
  }

  assert {
    condition     = output.flow_log_group_name == "/vpc/test/flow-logs"
    error_message = "flow_log_group_name must be the log group name when flow logs are on."
  }

  assert {
    condition     = aws_vpc.this.tags == tomap({ Name = "test" })
    error_message = "Resources must set only a Name tag derived from var.name."
  }
}

run "nat_on" {
  command = apply

  variables {
    enable_nat_gateway = true
  }

  assert {
    condition     = length(aws_eip.nat) == 1 && length(aws_nat_gateway.this) == 1 && length(aws_route.private_nat) == 1
    error_message = "enable_nat_gateway must create exactly one EIP, NAT gateway and private route."
  }

  assert {
    condition     = aws_nat_gateway.this[0].subnet_id == aws_subnet.public[0].id
    error_message = "NAT gateway must sit in the first public subnet."
  }

  assert {
    condition     = aws_route.private_nat[0].route_table_id == aws_route_table.private.id && aws_route.private_nat[0].destination_cidr_block == "0.0.0.0/0" && aws_route.private_nat[0].nat_gateway_id == aws_nat_gateway.this[0].id
    error_message = "Private route table must send 0.0.0.0/0 to the NAT gateway."
  }
}

run "flow_logs_off" {
  command = apply

  variables {
    enable_flow_logs = false
  }

  assert {
    condition     = length(aws_cloudwatch_log_group.flow_logs) == 0 && length(aws_iam_role.flow_logs) == 0 && length(aws_iam_role_policy.flow_logs) == 0 && length(aws_flow_log.this) == 0
    error_message = "enable_flow_logs = false must create no flow log resources."
  }

  assert {
    condition     = output.flow_log_group_name == null
    error_message = "flow_log_group_name must be null when flow logs are off."
  }
}

run "custom_cidr_and_retention" {
  command = apply

  variables {
    cidr_block              = "10.50.0.0/16"
    flow_log_retention_days = 30
  }

  assert {
    condition     = [for s in aws_subnet.public : s.cidr_block] == ["10.50.0.0/24", "10.50.1.0/24"] && [for s in aws_subnet.private : s.cidr_block] == ["10.50.10.0/24", "10.50.11.0/24"]
    error_message = "Subnets must be carved from var.cidr_block."
  }

  assert {
    condition     = aws_cloudwatch_log_group.flow_logs[0].retention_in_days == 30
    error_message = "Log group must use flow_log_retention_days."
  }
}

run "rejects_one_az" {
  command = plan

  variables {
    azs = ["az-a"]
  }

  expect_failures = [var.azs]
}

run "bad_azs" {
  command = plan

  variables {
    azs = ["az-a", "az-b", "az-c"]
  }

  expect_failures = [var.azs]
}
