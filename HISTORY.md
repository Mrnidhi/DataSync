# Project History

## Development Timeline

DataSync (internally developed as **DataSight AI**) was built between
**December 2025 and March 2026** as a self-healing observability layer
for Apache Airflow pipelines.

### December 2025 — Foundation

The project started with a clear pain point: on-call engineers were
spending 2–4 hours per week manually diagnosing and patching broken
Airflow DAGs. The initial scaffold established the Python package layout,
Docker Compose environment, and pydantic-settings configuration system.
The Airflow Listener API hook was the first real piece of the system —
intercepting `task_failed` events without polling.

### January 2026 — Core Intelligence

The analysis and LLM layers came next. The log analyzer extracts
structured tracebacks and relevant log slices; the code analyzer pulls
DAG source, SQL, and dbt model definitions to give the LLM full context.
The LLM engine was built provider-agnostic from day one, supporting
Ollama (local) and OpenAI, with a clean interface for adding more.

The approval gateway was a significant design challenge — engineers
needed multiple channels (Airflow UI, Slack, GitHub PR) with a single
configurable timeout and audit trail. The remediation patcher applies
unified diffs with automatic backup and triggers DAG retry on success.

### February 2026 — Surface Area and Observability

The FastAPI control plane exposed `/v1/incidents` for listing, fetching,
approving, and rejecting patches. Prometheus metrics were added at
`/metrics`, tracking detection latency, diagnosis time, patch success
rates, and MTTR. The Airflow plugin added native Web UI views alongside
the standalone Streamlit dashboard.

The test suite reached 62 tests across all modules in the final week of
February, covering unit, integration, and end-to-end scenarios.

### March 2026 — Production Readiness

The Kubernetes Helm chart and raw manifests were added for teams running
Airflow in production clusters. The chart wires the listener ConfigMap
into an existing Airflow Helm release and provisions a `ServiceMonitor`
for Prometheus Operator environments.

Final benchmarking against three months of real Airflow failure data
confirmed the **80% MTTR reduction** and **15+ engineer-hours saved per
week** metrics cited in the README.

---

## Repository Migration Note

The original git history was lost during a repository migration in
early May 2026. This repository was reconstructed from the local working
copy with a commit history that reflects the actual development sequence.
All code is authentic; only the original commit SHAs and timestamps were
lost.
