variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "bq_location" {
  type        = string
  default     = "us-central1"
  description = "Single region, per the one-region rule. BigQuery datasets that talk to each other must share a location."
}

variable "billing_account" {
  type        = string
  description = "Billing account ID for the budget alert. Leave empty to skip."
  default     = ""
}

variable "budget_usd" {
  type        = number
  default     = 50
  description = "Budget amount, in the billing account's currency (see budget_currency)."
}

variable "budget_currency" {
  type        = string
  default     = "USD"
  description = "Must match the billing account's currency, or the budget is rejected. Check the Billing page."
}
