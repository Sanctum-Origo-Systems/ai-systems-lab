output "vpc_id" {
  description = "ID of the VPC."
  value       = aws_vpc.this.id
}

output "vpc_cidr_block" {
  description = "IPv4 CIDR block of the VPC."
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  description = "Public subnet IDs, in var.azs order."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs, in var.azs order."
  value       = aws_subnet.private[*].id
}

output "private_subnet_ids_by_az" {
  description = "Map of AZ name (from var.azs) to private subnet ID."
  value       = { for i, az in var.azs : az => aws_subnet.private[i].id }
}

output "private_route_table_id" {
  description = "ID of the shared private route table, for gateway endpoints and optional NAT routes."
  value       = aws_route_table.private.id
}

output "flow_log_group_name" {
  description = "Name of the flow log group, or null when enable_flow_logs is false."
  value       = var.enable_flow_logs ? aws_cloudwatch_log_group.flow_logs[0].name : null
}
