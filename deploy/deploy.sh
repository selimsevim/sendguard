#!/usr/bin/env bash
# Deploy SendGuard to Cloud Run.
#
# Builds the container from the repo root (Dockerfile) with Cloud Build
# and deploys it with every variable from .env passed as Cloud Run env vars.
# BigQuery auth on Cloud Run comes from the runtime service account (ADC), so
# no key files are baked into the image (.env is in .dockerignore).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT="${GOOGLE_CLOUD_PROJECT:-fivetran-499011}"
REGION="${CLOUD_RUN_REGION:-us-central1}"
SERVICE="sendguard"

cd "$REPO_ROOT"
[ -f .env ] || { echo "ERROR: .env not found -- copy .env.example and fill it in"; exit 1; }

# .env -> @-separated KEY=VALUE list (gcloud custom delimiter syntax, safe for
# values containing commas); skips comments and blank values
ENV_VARS="^@^$(grep -Ev '^\s*(#|$)' .env | grep -Ev '=$' | paste -sd'@' -)"

gcloud run deploy "$SERVICE" \
  --project "$PROJECT" \
  --region "$REGION" \
  --source . \
  --port 8080 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 3600 \
  --min-instances 0 \
  --max-instances 2 \
  --allow-unauthenticated \
  --set-env-vars "$ENV_VARS"

echo
echo "Demo URL:"
gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" \
  --format='value(status.url)'
