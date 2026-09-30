output "bucket" {
  value = google_storage_bucket.ml.name
}

output "image_repo" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "trainer_sa" {
  value = google_service_account.trainer.email
}

output "facade_sa" {
  value = google_service_account.facade.email
}

output "cicd_sa" {
  value = google_service_account.cicd.email
}
