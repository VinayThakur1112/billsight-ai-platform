# Create Workload Identity Pool
gcloud iam workload-identity-pools create github-pool \
  --project=billsight-ai-project \
  --location=global \
  --display-name="GitHub Actions Pool"

# Create Workload Identity Provider (GitHub)
gcloud iam workload-identity-pools providers create-oidc github \
  --project=billsight-ai-project \
  --location=global \
  --workload-identity-pool=github-pool \
  --display-name="GitHub Provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="attribute.repository == 'YOUR_GITHUB_ORG/YOUR_REPO'"

# Bind GitHub Repo → GCP Service Account
gcloud iam service-accounts add-iam-policy-binding \
  cicd-gsa@billsight-ai-project.iam.gserviceaccount.com \
  --project=billsight-ai-project \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$(gcloud projects describe billsight-ai-project --format='value(projectNumber)')/locations/global/workloadIdentityPools/github-pool/attribute.repository:VinayThakur1112/billsight-ai-platform"

# verify Workload Identity Provider
gcloud iam workload-identity-pools providers describe github \
  --workload-identity-pool=github-pool \
  --location=global \
  --project=billsight-ai-project
