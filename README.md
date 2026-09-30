# mlops-uplift

A learning project for deployment and MLOps on GCP. A classifier and an uplift model are trained, gated, registered, served, monitored for drift, and retrained. Model quality does not matter. The infrastructure path does. See [Plan.md](Plan.md) for phases and status.

## Architecture
Seven diagrams (runtime, request flow, model lifecycle, drift loop, code map, CI, local-to-cloud mapping) are in [docs/architecture.md](docs/architecture.md).

In short: the target is GCS and BigQuery feeding Vertex training jobs and Model Registry, two Vertex Endpoints, and a facade on GKE Autopilot that logs to BigQuery for drift checks. Locally the same flow runs with files, a file-based registry, and Docker Compose. Data loading is in `src/common.py` and the registry in `src/registry.py`; `pipeline`, `drift`, and `loop` also read local paths, so the cloud swap touches those too.

## Local quickstart
Needs Python 3.13, Docker, make.

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
make bootstrap     # data, train, register, promote the candidate, serve it
                   # clf :8081, uplift :8082, facade :8080
curl -X POST localhost:8080/recommend -H 'content-type: application/json' \
  -d '{"age":30,"tenure_months":12,"avg_spend":80,"visits_30d":7,"is_member":1}'
make down
```

`make test` and `make lint` do what they say. `make smoke` is the full end-to-end check, also run by CI: it trains, releases v1, promotes v2, rolls back, and confirms each step from the running containers. The registry and deploy dir are isolated under `.smoke/`, but it still overwrites `data/data.csv`, clears `logs/*.jsonl`, and uses the same Compose project and ports, so it stops a stack started by `make bootstrap`.

`make train-local` trains straight into `artifacts/` for quick experiments. Serving does not read `artifacts/`; it serves whatever `make release` deployed.

## Runbook (local)

| Task | Command |
|---|---|
| Train, gate, register a candidate | `make pipeline` (exit 1 = rejected, 2 = could not run) |
| Promote candidate to champion | `python -m src.registry promote clf` (and `uplift`) |
| Roll back | `python -m src.registry rollback clf` (and `uplift`) |
| Serve the current champion | `make release` (needed after promote or rollback) |
| See what is served | `curl localhost:8081/health` shows `model_version` |
| Check for drift | `make drift` (exit 1 = drift, 2 = could not run, e.g. too little traffic) |
| Drift check, retrain if drifted | `python -m src.loop --retrain-data <csv>` |
| Simulate a bad model | `python -m src.make_data --shuffle-labels --out data/bad.csv`, then `python -m src.pipeline --data data/bad.csv` |
| Simulate drift | `python -m src.make_data --shift-features --out data/shifted.csv`, then `python -m scripts.send_traffic data/shifted.csv 500` |

Retraining never promotes on its own. A human runs `promote`, then `make release`.

Facade behaviour: if the uplift model fails or times out, it returns the classification result with `uplift: null` and `degraded: true`. If the classifier fails, it returns 503.

## Cloud (not yet run)
`infra/` holds the Terraform (APIs, bucket, registry, datasets, service accounts, budget alert). Needs a GCP project: `make auth`, copy `infra/terraform.tfvars.example` (set `budget_currency` to your billing account's currency), then `make init plan apply`. The budget alert is only created if `billing_account` is set. Always read the plan before applying. `make teardown` only destroys what Terraform created.

## Cost notes
- Vertex Endpoints and the GKE cluster bill by the hour. Undeploy and delete them at the end of every session.
- No GPUs, no Composer, smallest machine types, one region (us-central1).
- Stay on the Free Trial account and never upgrade billing.
- `make destroy` removes everything Terraform created.

## Layout
- infra/      Terraform
- docs/       architecture diagrams
- .github/    CI workflow (lint, tests, smoke; passing on GitHub Actions)
- src/        data, training, serving, registry, gate, pipeline, drift, loop
- api/        facade FastAPI (k8s manifests come with the GKE phase)
- docker/     Dockerfiles for serving and the facade
- scripts/    smoke test, traffic generator
- tests/      pytest suite
- dataform/, pipelines/, notebooks/   placeholders for cloud phases and exploration
- Generated and gitignored: data/, artifacts/, registry/, deployed/, logs/, .smoke/
