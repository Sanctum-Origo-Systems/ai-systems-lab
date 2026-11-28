variable "region" {
  description = "AWS region for the base stack."
  type        = string
  default     = "us-east-1"
}

variable "ttl" {
  description = "Date (YYYY-MM-DD) after which this stack should be destroyed. Applied as the ttl tag."
  type        = string

  validation {
    condition     = can(regex("^\\d{4}-\\d{2}-\\d{2}$", var.ttl))
    error_message = "ttl must be a date in YYYY-MM-DD form."
  }
}

variable "azs" {
  description = "The two availability zones, pinned so the VPC never changes shape when AWS adds a zone. Change them together with region."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]

  validation {
    condition     = length(var.azs) == 2
    error_message = "azs must list exactly 2 availability zones."
  }
}

variable "name" {
  description = "Name prefix for base resources."
  type        = string
  default     = "ai-systems-lab"
}

variable "cidr_block" {
  description = "VPC CIDR block."
  type        = string
  default     = "10.40.0.0/16"
}

variable "enable_nat_gateway" {
  description = "Create one NAT gateway (about $33/month plus per-GB processing). Off by default: private subnets use VPC endpoints instead."
  type        = bool
  default     = false
}

variable "enable_interface_endpoints" {
  description = "Create the interface VPC endpoints (ECR, logs, SSM, STS). About $100/month for 7 services in 2 AZs, so off while idle."
  type        = bool
  default     = false
}

variable "enable_flow_logs" {
  description = "VPC flow logs to CloudWatch Logs."
  type        = bool
  default     = true
}

variable "flow_log_retention_days" {
  description = "Flow-log retention in days (NFR-9: 7)."
  type        = number
  default     = 7
}

variable "ecr_repositories" {
  description = "ECR repositories to create. Workstreams add their image names here."
  type        = set(string)
  default     = []
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget in USD. No default: the amount is spec open decision 2."
  type        = number
}

variable "budget_alert_emails" {
  description = "Addresses that receive budget alerts. Set in the uncommitted terraform.tfvars."
  type        = list(string)
  sensitive   = true
}
