terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------

variable "name" {
  description = "Budget name."
  type        = string
}

variable "monthly_limit_usd" {
  description = "Monthly cost limit in USD. No default: the caller must choose it."
  type        = number

  validation {
    condition     = var.monthly_limit_usd > 0
    error_message = "monthly_limit_usd must be greater than 0."
  }
}

variable "alert_emails" {
  description = "Addresses that receive budget alerts. Set only in an uncommitted terraform.tfvars."
  type        = list(string)

  validation {
    condition     = length(var.alert_emails) > 0
    error_message = "alert_emails must contain at least one address."
  }
}

# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

resource "aws_budgets_budget" "this" {
  name         = var.name
  budget_type  = "COST"
  limit_amount = format("%.2f", var.monthly_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Early warning: actual spend has reached 80% of the limit.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.alert_emails
  }

  # Projection: spend is forecast to exceed the limit this month.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.alert_emails
  }
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

# alert_emails is deliberately not an output.
output "budget_name" {
  description = "Name of the budget."
  value       = aws_budgets_budget.this.name
}
