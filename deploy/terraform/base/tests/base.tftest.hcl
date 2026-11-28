# Offline wiring test: the mocked AWS provider needs no credentials and makes no AWS calls.
# Run with: terraform -chdir=deploy/terraform/base init -backend=false && terraform -chdir=deploy/terraform/base test

mock_provider "aws" {
  mock_data "aws_region" {
    defaults = {
      region = "us-east-1"
    }
  }

  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "111111111111"
    }
  }

  mock_resource "aws_cloudwatch_log_group" {
    defaults = {
      arn = "arn:aws:logs:us-east-1:111111111111:log-group:/vpc/ai-systems-lab/flow-logs"
    }
  }

  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::111111111111:role/ai-systems-lab-flow-logs"
    }
  }
}

variables {
  ttl                 = "2026-12-31"
  monthly_budget_usd  = 25
  budget_alert_emails = ["alerts@example.com"]
}

run "defaults_are_idle_and_private" {
  command = apply

  assert {
    condition     = length(module.vpc.private_subnet_ids) == 2 && length(module.vpc.public_subnet_ids) == 2
    error_message = "The base VPC must span exactly 2 AZs with public and private subnets."
  }

  assert {
    condition     = module.vpc.flow_log_group_name == "/vpc/ai-systems-lab/flow-logs"
    error_message = "Flow logs must be on by default."
  }

  assert {
    condition     = length(module.vpc_endpoints.interface_endpoint_ids) == 0 && module.vpc_endpoints.endpoint_security_group_id == null
    error_message = "Interface endpoints must be off by default (cost)."
  }

  assert {
    condition     = output.repository_urls == tomap({}) || length(output.repository_urls) == 0
    error_message = "No ECR repositories unless a workstream asks for them."
  }
}

run "endpoints_on" {
  command = apply

  variables {
    enable_interface_endpoints = true
    ecr_repositories           = ["lab-admission"]
  }

  assert {
    condition     = length(module.vpc_endpoints.interface_endpoint_ids) == 7
    error_message = "Turning endpoints on must create all 7 default interface endpoints."
  }

  assert {
    condition     = keys(output.repository_urls) == ["lab-admission"]
    error_message = "ecr_repositories must flow through to the ECR module."
  }
}

run "bad_ttl" {
  command = plan

  variables {
    ttl = "next week"
  }

  expect_failures = [var.ttl]
}
