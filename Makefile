PROJECT ?= $(shell gcloud config get-value project 2>/dev/null)
.DEFAULT_GOAL := help
REGION  ?= us-central1
REPO    := $(REGION)-docker.pkg.dev/$(PROJECT)/ml-images
TAG     ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

.PHONY: help check-project release bootstrap init plan apply destroy auth train build deploy teardown data train-local test up down lint smoke pipeline drift

help:
	@echo "Local:  bootstrap release up down data train-local pipeline drift test lint smoke"
	@echo "Cloud:  auth init plan apply destroy   (need a GCP project; see README)"

check-project:
	@test -n "$(PROJECT)" || { echo "No GCP project. Run 'make auth' or pass PROJECT=<id>."; exit 1; }

auth:
	gcloud auth login
	gcloud auth application-default login
	gcloud config set project $(PROJECT)

init:
	cd infra && terraform init

plan: check-project
	cd infra && terraform plan -var project_id=$(PROJECT)

apply: check-project
	cd infra && terraform apply -var project_id=$(PROJECT)

destroy: check-project
	cd infra && terraform destroy -var project_id=$(PROJECT)

# Local development (no cloud account needed)
data:
	.venv/bin/python -m src.make_data

train-local: data
	.venv/bin/python -m src.train_clf
	.venv/bin/python -m src.train_uplift

test:
	.venv/bin/pytest -q

up:
	docker compose up -d --build --wait

down:
	docker compose down

# Placeholders, filled in from later phases
train:
	@echo "phase 2: submit Vertex custom jobs"

build:
	@echo "phase 3: gcloud builds submit --tag $(REPO)/<image>:$(TAG)"

deploy:
	@echo "phase 4: kubectl apply -k api/k8s/overlays/dev"

# Delete anything that bills hourly. Extend as you add resources.
teardown:
	@echo "NOTE: this only destroys what Terraform created (APIs stay enabled). Vertex endpoints and the"
	@echo "GKE cluster are not created by Terraform, so delete them yourself first once they exist."
	$(MAKE) destroy

lint:
	.venv/bin/ruff check .

smoke:
	PY=.venv/bin/python scripts/smoke.sh

pipeline:
	.venv/bin/python -m src.pipeline

drift:
	.venv/bin/python -m src.drift

# Serve the current champion: copy it into deployed/ and recreate the containers.
release:
	for m in clf uplift; do .venv/bin/python -m src.registry deploy $$m || exit 1; done
	docker compose up -d --force-recreate --wait

# First-time local setup: data, train, register, promote, serve.
bootstrap: data
	.venv/bin/python -m src.pipeline
	for m in clf uplift; do .venv/bin/python -m src.registry promote $$m >/dev/null || exit 1; done
	$(MAKE) release
