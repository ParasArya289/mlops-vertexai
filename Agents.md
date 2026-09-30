# Agent Instructions

## Single goal
Help build and operate the deployment and infrastructure path described in `Plan.md`. Success means a working, repeatable, observable, cheap deployment. Model quality is not a goal.

## Scope
In scope:
* Terraform, Makefile, Dockerfiles, Cloud Build, Kubernetes manifests, Kustomize
* Vertex AI jobs, endpoints, pipelines, model registry, monitoring
* BigQuery and Dataform pipelines, Workflows, Scheduler
* GitHub Actions, Workload Identity, IAM
* Load tests, alerts, dashboards, runbooks

Out of scope (keep trivial):
* Feature engineering, tuning, model comparison, better metrics
* Real datasets, GPUs, large models
* Any new product feature

If a request drifts toward ML quality, say so and steer back to infra.

## Workflow
1. Read `Plan.md` and work on one phase at a time, in order.
2. Before changing anything, state which phase and which "done when" check you are targeting.
3. Prefer the smallest change that satisfies the check.
4. Verify by running the check (a command, a curl, a pipeline run). Do not claim done without evidence.
5. Update the status table in `Plan.md` when a phase passes.

## Safety and cost rules
1. Run `terraform plan` and show it before any `apply` or `destroy`.
2. Ask before creating anything that bills hourly (Vertex endpoints, GKE cluster). State the teardown command at the same time.
3. Always offer teardown at the end of a session.
4. Never upgrade the billing account, request GPUs, or create Composer or other costly services.
5. Smallest machine types, one region (us-central1), synthetic data only.
6. No service account key files. Use Workload Identity and Workload Identity Federation.
7. Never commit secrets, state files, or `terraform.tfvars`.
8. Do not touch resources outside this project. Do not run destructive commands on anything not created by this repo.

## Conventions
* Foundation resources live in Terraform. Fast changing things (images, endpoints, deployments, model versions) live in the Makefile, Vertex SDK, and CI/CD.
* Real logic lives in `src/`. Notebooks are for exploration only.
* One source of truth: the same `src/` code runs in the Dockerfile, the pipeline, and locally.
* Every deployable has `/health`, resource requests, and a timeout.
* Test locally with Docker Compose before deploying to the cloud.

## Communication
Be brief and direct. Report what changed, how it was verified, and what is left. Flag errors and risks plainly instead of working around them silently.