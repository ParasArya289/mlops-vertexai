terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
  # Local state is fine for a learning project.
  # Move to a GCS backend later as a stretch goal.
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# The Billing Budget API needs a quota project when called with user credentials.
# Only the budget resource uses this alias, so the rest of the config is unaffected.
provider "google" {
  alias                 = "billing"
  project               = var.project_id
  region                = var.region
  user_project_override = true
  billing_project       = var.project_id
}
