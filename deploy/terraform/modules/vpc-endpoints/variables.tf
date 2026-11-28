variable "name" {
  description = "Name prefix for every resource's Name tag and the endpoint security group name."
  type        = string
}

variable "vpc_id" {
  description = "ID of the VPC that receives the endpoints."
  type        = string
}

variable "vpc_cidr_block" {
  description = "IPv4 CIDR block of the VPC. The only source allowed to reach interface endpoints on 443."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs that get an interface endpoint network interface (one per AZ)."
  type        = list(string)
}

variable "private_route_table_ids" {
  description = "Private route table IDs that get the S3 gateway endpoint route."
  type        = list(string)
}

variable "enable_interface_endpoints" {
  description = "Create the endpoint security group and one interface endpoint per interface_services entry. Off by default because interface endpoints are billed per endpoint per AZ per hour."
  type        = bool
  default     = false
}

variable "interface_services" {
  description = "Service suffixes (after com.amazonaws.<region>.) that get an interface endpoint when enable_interface_endpoints is true."
  type        = set(string)
  default     = ["ecr.api", "ecr.dkr", "logs", "ssm", "ssmmessages", "ec2messages", "sts"]
}
