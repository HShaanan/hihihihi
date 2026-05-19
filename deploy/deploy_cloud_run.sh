#!/usr/bin/env bash
# Deploy the Yemot business-finder ADK agent to Cloud Run.
#
# Prereqs:
#   * gcloud CLI installed and authenticated (`gcloud auth login`)
#   * A GCP project with billing, Cloud Run + Vertex AI APIs enabled:
#       gcloud services enable run.googleapis.com aiplatform.googleapis.com
#
# Usage:
#   PROJECT_ID=my-proj REGION=us-central1 ./deploy/deploy_cloud_run.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-yemot-business-finder}"

gcloud config set project "${PROJECT_ID}"

# Builds from the Dockerfile via Cloud Build and deploys to Cloud Run.
gcloud run deploy "${SERVICE}" \
  --source . \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION}"

echo
echo "Deployed. Yemot API URL:"
gcloud run services describe "${SERVICE}" --region "${REGION}" \
  --format='value(status.url)' | sed 's#$#/yemot#'
