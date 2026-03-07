# DataSync — Kubernetes Deployment

Two equivalent paths to deploy DataSync alongside an existing Apache Airflow 2.7+ cluster:

## Option A — Helm (recommended)

```bash
# From the repo root
helm install datasync ./deploy/k8s/helm \
  --namespace datasync \
  --create-namespace \
  --set image.tag=0.1.0 \
  --set config.llmProvider=openai \
  --set secrets.existingSecret=datasync-secrets
```

Validate the chart without applying:

```bash
helm template ./deploy/k8s/helm
helm lint ./deploy/k8s/helm
```

Wire the listener into your existing Airflow Helm release by referencing
the generated `datasync-listener-env` ConfigMap from the Airflow scheduler/worker
`extraEnvFrom`:

```yaml
# values.yaml passed to the official airflow Helm chart
scheduler:
  extraEnvFrom: |
    - configMapRef:
        name: datasync-listener-env
workers:
  extraEnvFrom: |
    - configMapRef:
        name: datasync-listener-env
```

## Option B — Plain manifests

```bash
kubectl apply -f deploy/k8s/manifests/
# Then create the secret out-of-band:
kubectl create secret generic datasync-secrets -n datasync \
  --from-literal=OPENAI_API_KEY=sk-... \
  --from-literal=SLACK_WEBHOOK_URL=https://hooks.slack.com/...
```

## Verify

```bash
kubectl -n datasync get pods,svc
kubectl -n datasync port-forward svc/datasync-api 8000:8000
curl http://localhost:8000/healthz
curl http://localhost:8000/metrics | head
```
