# Offline tests: the mocked AWS provider needs no credentials and makes no AWS calls.
# Run with: terraform -chdir=deploy/terraform/modules/vpc-endpoints init -backend=false && terraform -chdir=deploy/terraform/modules/vpc-endpoints test

mock_provider "aws" {
  mock_data "aws_region" {
    defaults = {
      region = "us-east-1"
    }
  }
}

variables {
  name                    = "test"
  vpc_id                  = "vpc-0123456789abcdef0"
  vpc_cidr_block          = "10.40.0.0/16"
  private_subnet_ids      = ["subnet-0aaaaaaaaaaaaaaa1", "subnet-0bbbbbbbbbbbbbbb2"]
  private_route_table_ids = ["rtb-0ccccccccccccccc3"]
}

run "defaults" {
  command = apply

  assert {
    condition     = aws_vpc_endpoint.s3.vpc_endpoint_type == "Gateway" && aws_vpc_endpoint.s3.service_name == "com.amazonaws.us-east-1.s3"
    error_message = "S3 endpoint must be a Gateway endpoint for com.amazonaws.<region>.s3."
  }

  assert {
    condition     = aws_vpc_endpoint.s3.vpc_id == var.vpc_id && toset(aws_vpc_endpoint.s3.route_table_ids) == toset(var.private_route_table_ids)
    error_message = "S3 gateway endpoint must sit in var.vpc_id and attach to every private route table."
  }

  assert {
    condition     = length(aws_security_group.vpce) == 0 && length(aws_vpc_endpoint.interface) == 0
    error_message = "No security group or interface endpoints by default."
  }

  assert {
    condition     = var.interface_services == toset(["ecr.api", "ecr.dkr", "logs", "ssm", "ssmmessages", "ec2messages", "sts"])
    error_message = "interface_services must default to exactly ecr.api, ecr.dkr, logs, ssm, ssmmessages, ec2messages and sts."
  }

  assert {
    condition     = output.s3_gateway_endpoint_id == aws_vpc_endpoint.s3.id
    error_message = "s3_gateway_endpoint_id must be the S3 gateway endpoint ID."
  }

  assert {
    condition     = length(output.interface_endpoint_ids) == 0 && output.endpoint_security_group_id == null
    error_message = "Interface outputs must be an empty map and null when interface endpoints are off."
  }
}

run "interface_on" {
  command = apply

  variables {
    enable_interface_endpoints = true
  }

  assert {
    condition     = length(aws_security_group.vpce) == 1 && aws_security_group.vpce[0].name == "test-vpce" && aws_security_group.vpce[0].vpc_id == var.vpc_id
    error_message = "Exactly one security group named <name>-vpce in var.vpc_id."
  }

  assert {
    condition     = length(aws_security_group.vpce[0].ingress) == 1
    error_message = "Endpoint security group must have exactly one ingress rule."
  }

  assert {
    condition = alltrue([
      for r in aws_security_group.vpce[0].ingress :
      r.from_port == 443 && r.to_port == 443 && r.protocol == "tcp" && tolist(r.cidr_blocks) == tolist(["10.40.0.0/16"]) && length(coalesce(r.ipv6_cidr_blocks, [])) == 0 && length(coalesce(r.security_groups, [])) == 0 && length(coalesce(r.prefix_list_ids, [])) == 0 && !coalesce(r.self, false)
    ])
    error_message = "The ingress rule must be tcp 443 from var.vpc_cidr_block only."
  }

  assert {
    condition     = length(aws_security_group.vpce[0].egress) == 0
    error_message = "Endpoint security group must have no egress rules."
  }

  assert {
    condition     = toset(keys(aws_vpc_endpoint.interface)) == var.interface_services
    error_message = "One interface endpoint per interface_services entry."
  }

  assert {
    condition = alltrue([
      for svc, ep in aws_vpc_endpoint.interface :
      ep.vpc_endpoint_type == "Interface" && ep.service_name == "com.amazonaws.us-east-1.${svc}" && ep.private_dns_enabled && ep.vpc_id == var.vpc_id
    ])
    error_message = "Interface endpoints must be Interface type, named com.amazonaws.<region>.<service>, with private DNS on."
  }

  assert {
    condition = alltrue([
      for ep in aws_vpc_endpoint.interface :
      toset(ep.subnet_ids) == toset(var.private_subnet_ids) && toset(ep.security_group_ids) == toset([aws_security_group.vpce[0].id])
    ])
    error_message = "Interface endpoints must use the private subnets and only the endpoint security group."
  }

  assert {
    condition     = output.interface_endpoint_ids == { for svc, ep in aws_vpc_endpoint.interface : svc => ep.id } && length(output.interface_endpoint_ids) == 7
    error_message = "interface_endpoint_ids must map each service to its endpoint ID."
  }

  assert {
    condition     = output.endpoint_security_group_id == aws_security_group.vpce[0].id
    error_message = "endpoint_security_group_id must be the endpoint security group ID when on."
  }

  assert {
    condition     = length(aws_vpc_endpoint.s3.route_table_ids) == 1 && aws_vpc_endpoint.s3.vpc_endpoint_type == "Gateway"
    error_message = "S3 gateway endpoint must still exist with interface endpoints on."
  }
}

run "custom_services_and_cidr" {
  command = apply

  variables {
    enable_interface_endpoints = true
    interface_services         = ["sts"]
    vpc_cidr_block             = "10.50.0.0/16"
  }

  assert {
    condition     = keys(aws_vpc_endpoint.interface) == ["sts"] && aws_vpc_endpoint.interface["sts"].service_name == "com.amazonaws.us-east-1.sts"
    error_message = "interface_services must select which interface endpoints exist."
  }

  assert {
    condition     = alltrue([for r in aws_security_group.vpce[0].ingress : tolist(r.cidr_blocks) == tolist(["10.50.0.0/16"])])
    error_message = "Ingress must follow var.vpc_cidr_block."
  }
}
