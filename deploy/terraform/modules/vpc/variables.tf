variable "name" {
  description = "Name prefix for every resource's Name tag."
  type        = string
}

variable "cidr_block" {
  description = "IPv4 CIDR block for the VPC. Subnets are /24s carved from it with cidrsubnet(cidr_block, 8, n)."
  type        = string
  default     = "10.40.0.0/16"
}

variable "azs" {
  description = "Exactly two availability zone names. Subnet i is placed in azs[i]."
  type        = list(string)

  validation {
    condition     = length(var.azs) == 2
    error_message = "azs must contain exactly 2 availability zones."
  }
}

variable "enable_nat_gateway" {
  description = "Create one NAT gateway (and its EIP) for private egress. Off by default so an idle VPC costs nothing."
  type        = bool
  default     = false
}

variable "enable_flow_logs" {
  description = "Send VPC flow logs (all traffic) to a CloudWatch log group."
  type        = bool
  default     = true
}

variable "flow_log_retention_days" {
  description = "Retention in days for the flow log group."
  type        = number
  default     = 7
}
