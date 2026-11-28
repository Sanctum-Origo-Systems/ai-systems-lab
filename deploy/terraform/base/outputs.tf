# Nothing here is secret. budget_alert_emails is deliberately not an output.

output "vpc_id" {
  value = module.vpc.vpc_id
}

output "public_subnet_ids" {
  value = module.vpc.public_subnet_ids
}

output "private_subnet_ids" {
  value = module.vpc.private_subnet_ids
}

output "private_route_table_id" {
  value = module.vpc.private_route_table_id
}

output "endpoint_security_group_id" {
  value = module.vpc_endpoints.endpoint_security_group_id
}

output "repository_urls" {
  value = module.ecr.repository_urls
}

output "flow_log_group_name" {
  value = module.vpc.flow_log_group_name
}
