module "vpc" {
  source = "../modules/vpc"

  name                    = var.name
  cidr_block              = var.cidr_block
  azs                     = var.azs
  enable_nat_gateway      = var.enable_nat_gateway
  enable_flow_logs        = var.enable_flow_logs
  flow_log_retention_days = var.flow_log_retention_days
}

module "vpc_endpoints" {
  source = "../modules/vpc-endpoints"

  name                       = var.name
  vpc_id                     = module.vpc.vpc_id
  vpc_cidr_block             = module.vpc.vpc_cidr_block
  private_subnet_ids         = module.vpc.private_subnet_ids
  private_route_table_ids    = [module.vpc.private_route_table_id]
  enable_interface_endpoints = var.enable_interface_endpoints
}

module "ecr" {
  source = "../modules/ecr"

  repositories = var.ecr_repositories
}

module "budget" {
  source = "../modules/budget"

  name              = var.name
  monthly_limit_usd = var.monthly_budget_usd
  alert_emails      = var.budget_alert_emails
}
