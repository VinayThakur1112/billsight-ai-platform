BillSight AI Platform

BillSight AI Platform is a cloud-native, event-driven Machine Learning pipeline designed to extract structured data from bill images (.jpg) using OCR and ML models on Google Cloud Platform.

The platform is built with production-grade components such as Kubernetes, Vertex AI, BigQuery, Pub/Sub, Terraform, and CI/CD, following real-world enterprise architecture patterns.

⸻

🚀 Key Capabilities
	•	📸 OCR processing of bill images (JPG format)
	•	⚡ Event-driven ingestion using Pub/Sub
	•	🧠 ML-powered text extraction via Vertex AI
	•	🧩 Microservices architecture on Kubernetes (GKE)
	•	📊 Structured, queryable data in BigQuery
	•	🔁 Fault-tolerant with retries and dead-letter queues
	•	🔐 Secure by design (IAM, Workload Identity, Secret Manager)
	•	🏗️ Fully reproducible infrastructure using Terraform
	•	🔄 CI/CD-enabled container build & deployment

⸻

🏗️ High-Level Architecture

Client / User
     │
     ▼
Cloud Storage (GCS)
(bills-raw-jpg bucket)
     │
     ▼
Pub/Sub Topic
(bill-upload-events)
     │
     ▼
Kubernetes (GKE)
Ingestion Service
     │
     ▼
Vertex AI OCR
(Vision API / Custom Model)
     │
     ▼
Post-processing Service
(Parsing & Validation)
     │
     ▼
BigQuery
(Structured Bill Data)


⸻

🧱 Tech Stack

Layer	Technology
Object Storage	Google Cloud Storage
Messaging	Pub/Sub
Compute	Google Kubernetes Engine (GKE)
Containerization	Docker
ML Platform	Vertex AI
Analytics	BigQuery
Infrastructure as Code	Terraform
CI/CD	Cloud Build / GitHub Actions
CD	Argo CD / Cloud Deploy
Secrets	Secret Manager
Observability	Cloud Logging & Monitoring


⸻

📂 Repository Structure

billsight-ai-platform/
│
├── services/
│   ├── ingestion-service/
│   ├── ocr-service/
│   └── postprocess-service/
│
├── vertex-pipelines/
│   ├── ocr_pipeline.py
│   └── pipeline.yaml
│
├── terraform/
│   ├── modules/
│   ├── envs/
│   └── main.tf
│
├── cicd/
│   ├── cloudbuild.yaml
│   └── github-actions.yaml
│
├── docs/
│   ├── architecture.md
│   ├── data-model.md
│   └── runbook.md
│
└── README.md


⸻

🔄 End-to-End Workflow
	1.	User uploads a bill image (.jpg) to a GCS bucket
	2.	GCS emits an object creation event
	3.	Pub/Sub publishes a message
	4.	Ingestion service (GKE) consumes the message
	5.	OCR service invokes Vertex AI OCR
	6.	Extracted text is parsed and validated
	7.	Structured data is stored in BigQuery
	8.	Raw and processed artifacts are archived

⸻

🔐 Security Design
	•	Fine-grained IAM roles per service
	•	Workload Identity for GKE → GCP access
	•	Secrets managed via Secret Manager
	•	No hardcoded credentials

⸻

🔁 CI/CD Strategy

Continuous Integration
	•	Linting and unit tests
	•	Docker image build
	•	Push to Artifact Registry

Continuous Deployment
	•	GitOps-style Kubernetes deployment
	•	Environment separation (dev / staging / prod)

⸻

🌍 Infrastructure as Code

All cloud resources are provisioned using Terraform, including:
	•	GCS buckets
	•	Pub/Sub topics and subscriptions
	•	GKE clusters and node pools
	•	BigQuery datasets and tables
	•	Vertex AI resources
	•	IAM roles and bindings

⸻

📈 Observability & Reliability
	•	Centralized logging (Cloud Logging)
	•	Metrics and alerts (Cloud Monitoring)
	•	Dead-letter Pub/Sub topics
	•	Reprocessing support

⸻

🎯 Use Cases
	•	Automated bill & invoice processing
	•	Expense analytics
	•	Financial data digitization
	•	Downstream ML (fraud detection, spend analysis)

⸻

🛣️ Roadmap
	•	Custom OCR model fine-tuning
	•	Schema learning & adaptive parsing
	•	Confidence scoring & human review loop
	•	Multi-language bill support
	•	Streaming analytics dashboards

⸻

👤 Author

Vinay Thakur
Cloud & Data Lead Engineer

⸻