locals {
  apis = [
    "aiplatform.googleapis.com",
    "bigquery.googleapis.com",
    "bigquerystorage.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "container.googleapis.com",
    "dataform.googleapis.com",
    "workflows.googleapis.com",
    "cloudscheduler.googleapis.com",
    "iamcredentials.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudresourcemanager.googleapis.com", # needed by google_project_iam_member and the project data source
    "iam.googleapis.com",
    "serviceusage.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  service            = each.value
  disable_on_destroy = false
}

# Storage for raw files and model artifacts
resource "google_storage_bucket" "ml" {
  name                        = "${var.project_id}-ml"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
  depends_on                  = [google_project_service.apis]
}

# Container images
resource "google_artifact_registry_repository" "images" {
  repository_id = "ml-images"
  location      = var.region
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

# BigQuery datasets for the ELT layers
resource "google_bigquery_dataset" "layers" {
  for_each                   = toset(["raw", "staging", "features", "serving_logs"])
  dataset_id                 = each.value
  location                   = var.bq_location
  delete_contents_on_destroy = true
  depends_on                 = [google_project_service.apis]
}

# Service accounts
data "google_project" "this" {
  project_id = var.project_id
  depends_on = [google_project_service.apis]
}

resource "google_service_account" "trainer" {
  account_id   = "ml-trainer"
  display_name = "Vertex training jobs"
  depends_on   = [google_project_service.apis]
}

resource "google_service_account" "facade" {
  account_id   = "facade-api"
  display_name = "Facade API on GKE"
  depends_on   = [google_project_service.apis]
}

resource "google_service_account" "cicd" {
  account_id   = "cicd-deployer"
  display_name = "GitHub Actions deployer"
  depends_on   = [google_project_service.apis]
}

locals {
  trainer_roles = [
    "roles/aiplatform.user",
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
    "roles/bigquery.readSessionUser",
    "roles/artifactregistry.reader",
  ]
  facade_roles = [
    "roles/aiplatform.user",
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ]
  cicd_roles = [
    "roles/artifactregistry.writer",
    "roles/cloudbuild.builds.editor",
    "roles/container.developer",
    "roles/aiplatform.user",
    "roles/storage.objectAdmin",
  ]
}

resource "google_project_iam_member" "trainer" {
  for_each = toset(local.trainer_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.trainer.email}"
}

resource "google_project_iam_member" "facade" {
  for_each = toset(local.facade_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.facade.email}"
}

resource "google_project_iam_member" "cicd" {
  for_each = toset(local.cicd_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_storage_bucket_iam_member" "trainer_bucket" {
  bucket = google_storage_bucket.ml.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.trainer.email}"
}

# Budget alert (only if a billing account is given)
resource "google_billing_budget" "budget" {
  provider        = google.billing
  count           = var.billing_account == "" ? 0 : 1
  billing_account = var.billing_account
  display_name    = "${var.project_id} learning budget"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }

  amount {
    specified_amount {
      currency_code = var.budget_currency
      units         = tostring(var.budget_usd)
    }
  }

  dynamic "threshold_rules" {
    for_each = [0.5, 0.8, 1.0]
    content {
      threshold_percent = threshold_rules.value
    }
  }

  depends_on = [google_project_service.apis]
}
