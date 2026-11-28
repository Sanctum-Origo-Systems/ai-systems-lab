output "s3_gateway_endpoint_id" {
  description = "ID of the S3 gateway endpoint."
  value       = aws_vpc_endpoint.s3.id
}

output "interface_endpoint_ids" {
  description = "Map of service suffix to interface endpoint ID. Empty when enable_interface_endpoints is false."
  value       = { for service, endpoint in aws_vpc_endpoint.interface : service => endpoint.id }
}

output "endpoint_security_group_id" {
  description = "ID of the interface endpoint security group, or null when enable_interface_endpoints is false."
  value       = var.enable_interface_endpoints ? aws_security_group.vpce[0].id : null
}
