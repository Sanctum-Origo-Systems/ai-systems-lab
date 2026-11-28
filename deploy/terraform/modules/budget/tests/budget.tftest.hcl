# Offline tests: the mocked AWS provider needs no credentials and makes no AWS calls.
# Run with: terraform -chdir=deploy/terraform/modules/budget init -backend=false && terraform -chdir=deploy/terraform/modules/budget test
# The alert addresses below are placeholders; real ones live only in an uncommitted terraform.tfvars.

mock_provider "aws" {}

variables {
  name              = "lab-monthly"
  monthly_limit_usd = 25
  alert_emails      = ["alerts-one.example.invalid", "alerts-two.example.invalid"]
}

run "budget" {
  command = apply

  assert {
    condition     = aws_budgets_budget.this.budget_type == "COST" && aws_budgets_budget.this.time_unit == "MONTHLY"
    error_message = "Budget must be a monthly COST budget."
  }

  assert {
    condition     = tonumber(aws_budgets_budget.this.limit_amount) == 25 && aws_budgets_budget.this.limit_unit == "USD"
    error_message = "Budget limit must be var.monthly_limit_usd in USD."
  }

  assert {
    condition     = length(aws_budgets_budget.this.notification) == 2
    error_message = "Budget must have exactly two notifications."
  }

  assert {
    condition = anytrue([
      for n in aws_budgets_budget.this.notification :
      n.notification_type == "ACTUAL" && n.threshold == 80 && n.threshold_type == "PERCENTAGE" && n.comparison_operator == "GREATER_THAN"
    ])
    error_message = "Budget must alert on ACTUAL spend above 80%."
  }

  assert {
    condition = anytrue([
      for n in aws_budgets_budget.this.notification :
      n.notification_type == "FORECASTED" && n.threshold == 100 && n.threshold_type == "PERCENTAGE" && n.comparison_operator == "GREATER_THAN"
    ])
    error_message = "Budget must alert on FORECASTED spend above 100%."
  }

  assert {
    condition = alltrue([
      for n in aws_budgets_budget.this.notification :
      toset(n.subscriber_email_addresses) == toset(var.alert_emails)
    ])
    error_message = "Both notifications must go to var.alert_emails."
  }

  assert {
    condition     = output.budget_name == "lab-monthly"
    error_message = "budget_name must be the budget's name."
  }
}

run "rejects_empty_alert_emails" {
  command = plan

  variables {
    alert_emails = []
  }

  expect_failures = [var.alert_emails]
}

run "rejects_non_positive_limit" {
  command = plan

  variables {
    monthly_limit_usd = 0
  }

  expect_failures = [var.monthly_limit_usd]
}
