# Architecture

Diagrams of the local setup as built and verified, plus the cloud target it maps to. Render in any Mermaid viewer (GitHub, VS Code Markdown preview).

## 1. Local runtime (Docker Compose)

Three containers on one Compose network. Only the facade is meant for callers; the model ports are published on 127.0.0.1 for debugging.

```mermaid
flowchart LR
  client(["Client<br/>curl / send_traffic.py"])

  subgraph host["Host machine"]
    direction LR

    subgraph compose["Docker Compose network"]
      direction LR
      facade["<b>facade</b><br/>api/main.py<br/>POST /recommend, GET /health<br/>timeout 2s, threshold 0.02<br/>host :8080"]
      clf["<b>clf</b><br/>src/serve.py, MODEL_TYPE=clf<br/>POST /predict, GET /health<br/>health shows model_version<br/>host :8081"]
      uplift["<b>uplift</b><br/>src/serve.py, MODEL_TYPE=uplift<br/>POST /predict, GET /health<br/>health shows model_version<br/>host :8082"]
    end

    subgraph disk["Host filesystem"]
      direction TB
      art[("deployed/clf, deployed/uplift<br/>champion copy: model.joblib,<br/>metrics.json, VERSION")]
      logs[("logs/clf.jsonl<br/>logs/uplift.jsonl<br/>one JSON row per request")]
    end
  end

  client -->|"POST /recommend<br/>5 features"| facade
  facade -->|"parallel POST /predict<br/>CLF_URL"| clf
  facade -->|"parallel POST /predict<br/>UPLIFT_URL"| uplift
  art -.->|"bind mount /model, read-only"| clf
  art -.->|"bind mount /model, read-only"| uplift
  clf -->|"append log row"| logs
  uplift -->|"append log row"| logs
  facade -->|"p_convert, uplift,<br/>recommendation, degraded"| client
```

## 2. One request, including failure paths

```mermaid
sequenceDiagram
  autonumber
  participant C as Client
  participant F as Facade
  participant K as clf container
  participant U as uplift container
  participant L as logs/*.jsonl

  C->>F: POST /recommend {age, tenure_months, avg_spend, visits_30d, is_member}
  Note over F: validate with pydantic, else 422
  par asyncio.gather, 2s timeout each
    F->>K: POST /predict {instances: [features]}
    K->>L: append ts, latency_ms, instances, predictions
    K-->>F: {predictions: [p_convert]}
  and
    F->>U: POST /predict {instances: [features]}
    U->>L: append ts, latency_ms, instances, predictions
    U-->>F: {predictions: [uplift]}
  end

  alt both succeed
    F-->>C: 200 recommendation = treat if uplift > 0.02 else do_not_treat, degraded false
  else uplift failed or timed out
    F-->>C: 200 uplift null, recommendation unknown, degraded true
  else classifier failed
    F-->>C: 503 classifier unavailable
  end
```

## 3. Model lifecycle: train, gate, register, promote, deploy

The pipeline is all-or-nothing: both models register or neither does, because they are served together. Serving only changes when `make release` runs, so promote and rollback are decisions and release is the action. Check what is live with `curl localhost:8081/health`.

```mermaid
flowchart TD
  gen["make_data.py<br/>seed 42, 10k rows, known true_uplift<br/>flags: --shuffle-labels, --shift-features"]
  csv[("data/data.csv")]
  gen --> csv

  subgraph pipe["src/pipeline.py, make pipeline"]
    direction TB
    dc{"data_check<br/>required columns, no nulls<br/>treatment and converted are 0/1<br/>treatment share 0.4 to 0.6<br/>at least 1000 rows<br/>both classes in each split"}
    tclf["train_clf.py<br/>LogisticRegression<br/>metric: AUC"]
    tup["train_uplift.py<br/>TLearner, two LogisticRegressions<br/>metric: Qini"]
    g{"gate.check per model<br/>floor: AUC above 0.55, Qini above 0.005<br/>non-finite metrics rejected<br/>and not worse than champion"}
    reg["registry.register<br/>next version, alias candidate"]
    dc -->|pass| tclf
    dc -->|pass| tup
    tclf --> g
    tup --> g
    g -->|"both pass"| reg
  end

  csv --> dc
  dc -->|"fail: exit 1"| stop1(["stop"])
  g -->|"any reject: exit 1"| stop2(["nothing registered"])

  store[("registry/&lt;model&gt;/vN<br/>model.joblib, metrics.json<br/>aliases.json: candidate,<br/>champion, previous_champion")]
  reg --> store

  prom["python -m src.registry promote<br/>human step, never automatic"]
  rb["python -m src.registry rollback<br/>champion back to previous_champion"]
  store --> prom --> store
  store --> rb --> store

  served[("deployed/&lt;model&gt;<br/>champion copy + VERSION<br/>what Compose serves")]
  dep["registry deploy, then<br/>docker compose up --force-recreate<br/>make release"]
  store -->|"champion"| dep --> served
```

## 4. Drift and the retraining loop

```mermaid
flowchart LR
  traffic(["Live requests<br/>through facade"]) --> logs[("logs/clf.jsonl")]
  ref[("Reference data<br/>data/data.csv")]

  subgraph loop["src/loop.py"]
    direction LR
    psi{"src/drift.py<br/>PSI per feature<br/>bins from reference quantiles<br/>drift if PSI above 0.2<br/>needs at least 200 requests"}
    retrain["pipeline.run on<br/>--retrain-data"]
    psi -->|"drift, exit 1"| retrain
  end

  logs --> psi
  ref --> psi
  psi -->|"no drift, exit 0"| idle(["nothing to do"])
  psi -->|"too few requests, exit 2"| wait(["wait for more traffic"])
  retrain -->|"registers candidate only"| reg[("registry: candidate vN")]
  reg --> human{"Human review"}
  human -->|promote| champ["champion"]
  human -->|"rollback"| prev["previous_champion"]
```

Loop exit codes: 0 no drift, 1 drift and a candidate was registered, 2 could not run (too little traffic, bad data, crash), 3 drift but the pipeline rejected the retrain. Pipeline exit codes: 0 registered a candidate, 1 gate rejected, 2 could not run. Drift is measured with PSI; binary features use one bin per value, since quantile bins collapse for them.

## 5. Code map

Real logic lives in `src/`. The serving image and the training scripts import the same modules. Arrows are the actual `import` statements; `pipeline` reaches the training scripts by subprocess.

```mermaid
flowchart TD
  subgraph data["Data"]
    make_data["make_data.py<br/>FEATURES, make_data"]
    common["common.py<br/>load_split, qini_coefficient,<br/>save_artifacts"]
  end

  subgraph model["Models"]
    models["models.py<br/>TLearner"]
    train_clf["train_clf.py"]
    train_uplift["train_uplift.py"]
  end

  subgraph release["Release control"]
    gate["gate.py"]
    registry["registry.py"]
    pipeline["pipeline.py"]
    drift["drift.py"]
    loop["loop.py"]
  end

  subgraph runtime["Runtime"]
    serve["serve.py"]
    api["api/main.py<br/>separate image, no src/"]
  end

  train_clf --> common
  train_clf --> make_data
  train_uplift --> common
  train_uplift --> make_data
  train_uplift --> models
  serve --> models
  serve --> make_data
  drift --> make_data
  pipeline --> gate
  pipeline --> registry
  pipeline --> make_data
  pipeline -->|"subprocess"| train_clf
  pipeline -->|"subprocess"| train_uplift
  loop --> drift
  loop --> pipeline
  loop --> registry
  api -.->|"HTTP only"| serve
```

## 6. Delivery: the CI workflow

```mermaid
flowchart LR
  dev(["Pull request, push to master,<br/>or manual dispatch"]) --> ci

  subgraph ci["GitHub Actions, .github/workflows/pr.yml"]
    direction LR
    lint["ruff check"] --> unit["pytest, 29 tests"] --> smoke["scripts/smoke.sh"]
  end

  subgraph smokeSteps["What smoke.sh does"]
    direction TB
    s1["make_data, pipeline,<br/>promote, deploy v1"] --> s2["compose up, assert<br/>both serve v1"]
    s2 --> s3["POST /recommend"]
    s3 --> s4{"assert response shape,<br/>degraded false,<br/>log files non-empty"}
    s4 --> s4b["stop uplift: assert degraded<br/>stop clf: assert 503"]
    s4b --> s5["pipeline again, promote,<br/>deploy: assert v2"]
    s5 --> s6["rollback, deploy:<br/>assert v1"]
    s6 --> s7["compose down, delete .smoke/<br/>on failure: print ps and logs first"]
  end

  smoke --> smokeSteps
  ci -.->|"merge and deploy half:<br/>needs GCP, not built"| deploy(["Push images, deploy, rollback on failed probes"])
```

## 7. Local to cloud mapping

What each local piece becomes on GCP (Plan.md). Only the local column exists today. The CI workflow runs on GitHub, but only the local checks, not any deploy.

```mermaid
flowchart LR
  subgraph local["Local, built and tested"]
    l1["data/data.csv"]
    l2["src.make_data + train scripts<br/>run in venv"]
    l3["registry/ with aliases"]
    l4["clf and uplift containers"]
    l5["facade container"]
    l6["logs/*.jsonl"]
    l7["src.drift + src.loop"]
    l8["scripts/smoke.sh + pr.yml<br/>(passing on GitHub Actions)"]
  end

  subgraph cloud["GCP target, not built yet"]
    c1["GCS then BigQuery raw,<br/>Dataform staging and features"]
    c2["Vertex Custom Jobs<br/>same code, one training image"]
    c3["Vertex Model Registry<br/>aliases candidate, champion"]
    c4["Vertex Endpoints<br/>same image, AIP_HTTP_PORT contract"]
    c5["GKE Autopilot<br/>Deployment, HPA, Gateway, Kustomize"]
    c6["BigQuery serving_logs"]
    c7["Vertex Model Monitoring +<br/>Cloud Monitoring alerts"]
    c8["Actions with Workload<br/>Identity Federation"]
  end

  l1 --> c1
  l2 --> c2
  l3 --> c3
  l4 --> c4
  l5 --> c5
  l6 --> c6
  l7 --> c7
  l8 --> c8
```
