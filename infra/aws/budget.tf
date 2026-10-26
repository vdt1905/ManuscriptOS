# Safety net for "free of cost": an email as soon as forecast or actual
# spending passes $1 in a month. (The first two AWS Budgets are free.)
resource "aws_budgets_budget" "zero_spend" {
  count        = var.alert_email != "" ? 1 : 0
  name         = "docling-free-tier-guard"
  budget_type  = "COST"
  limit_amount = "1"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 1
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
}
