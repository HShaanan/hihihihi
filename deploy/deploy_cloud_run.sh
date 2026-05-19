#!/usr/bin/env bash
# פריסת סוכן ה-ADK לאיתור עסקים (ימות המשיח) ל-Cloud Run.
#
# דרישות מוקדמות:
#   * gcloud CLI מותקן ומחובר (`gcloud auth login`)
#   * פרויקט GCP עם חיוב, ועם Cloud Run + Vertex AI מופעלים:
#       gcloud services enable run.googleapis.com aiplatform.googleapis.com
#
# שימוש:
#   PROJECT_ID=my-proj REGION=us-central1 ./deploy/deploy_cloud_run.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-yemot-business-finder}"

gcloud config set project "${PROJECT_ID}"

# בונה מתוך ה-Dockerfile דרך Cloud Build ופורס ל-Cloud Run.
gcloud run deploy "${SERVICE}" \
  --source . \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION}"

echo
echo "הפריסה הושלמה. כתובת ה-API לימות המשיח:"
gcloud run services describe "${SERVICE}" --region "${REGION}" \
  --format='value(status.url)' | sed 's#$#/yemot#'
