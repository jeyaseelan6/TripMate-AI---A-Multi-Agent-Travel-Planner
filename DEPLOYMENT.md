# Google Cloud Run Deployment Guide

This guide explains how to deploy **TripMate AI** to **Google Cloud Run**.

---

## 1. Cloud Run Architecture Overview

TripMate AI runs as a containerized FastAPI application:
* **Entrypoint**: Uvicorn bound to dynamic `0.0.0.0:${PORT:-8080}`.
* **Database State**: External PostgreSQL (Render, Supabase, Neon, or Cloud SQL) using `DATABASE_URL`.
* **Execution Timeout**: Agent execution involves multi-step LLM calls and tool queries; set timeout to at least **300 seconds** (5 minutes).
* **Memory / CPU**: 1 vCPU and 1 GiB or 2 GiB RAM recommended.

---

## 2. Prerequisites

1. Google Cloud SDK installed and authenticated:
   ```bash
   gcloud auth login
   gcloud config set project calmwork-ai
   ```
2. Enable necessary GCP APIs:
   ```bash
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
   ```

---

## 3. Required Environment Variables / Secrets

Make sure you have your keys ready:
* `DATABASE_URL`: PostgreSQL connection string (must include `sslmode=require` if hosted externally).
* `GROQ_API_KEY`: Groq API Key.
* `GROQ_MODEL`: Model identifier (default: `openai/gpt-oss-120b`).
* `TAVILY_API_KEY`: Tavily Search API key.
* `OPENWEATHER_API_KEY`: OpenWeatherMap API key.
* `AVIATION_STACK_API_KEY`: AviationStack API key (optional).

---

## 4. One-Command Deployment

You can deploy directly from source using Google Cloud Build and Cloud Run:

### Option A: Automated PowerShell Deployment (Recommended)

Run the automated script that reads `.env` securely without character escaping issues:
```powershell
.\deploy-cloudrun.ps1
```

### Option B: Using an Environment YAML File (`--env-vars-file`)

Create an `env.yaml` file (excluded from git/docker):
```yaml
DATABASE_URL: "postgresql://..."
GROQ_API_KEY: "gsk_..."
GROQ_MODEL: "openai/gpt-oss-120b"
TAVILY_API_KEY: "tvly-..."
OPENWEATHER_API_KEY: "..."
AVIATION_STACK_API_KEY: "..."
DEFAULT_ORIGIN_IATA: "DAC"
```

Then deploy:
```bash
gcloud run deploy tripmate-ai \
  --source . \
  --region asia-south1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --env-vars-file env.yaml
```

### Option C: Using Google Secret Manager (Recommended for Production)

1. Create the secrets in Secret Manager:
   ```bash
   echo -n "YOUR_DB_URL" | gcloud secrets create DATABASE_URL --data-file=-
   echo -n "YOUR_GROQ_KEY" | gcloud secrets create GROQ_API_KEY --data-file=-
   echo -n "YOUR_TAVILY_KEY" | gcloud secrets create TAVILY_API_KEY --data-file=-
   echo -n "YOUR_WEATHER_KEY" | gcloud secrets create OPENWEATHER_API_KEY --data-file=-
   ```

2. Deploy referencing the secrets:
   ```bash
   gcloud run deploy tripmate-ai \
  --source . \
  --region asia-south1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --set-env-vars "GROQ_MODEL=openai/gpt-oss-120b" \
  --set-secrets "DATABASE_URL=DATABASE_URL:latest,GROQ_API_KEY=GROQ_API_KEY:latest,TAVILY_API_KEY=TAVILY_API_KEY:latest,OPENWEATHER_API_KEY=OPENWEATHER_API_KEY:latest"
   ```

---

## 5. Health Check & Validation

Once deployed, Google Cloud Run will provide a public URL (e.g., `https://tripmate-ai-xxxx-uc.a.run.app`).

Test the service:
```bash
curl https://YOUR_SERVICE_URL/health
```

Expected response:
```json
{
  "status": "ok",
  "message": "TripMate AI API is running",
  "features": [
    "supervisor_agent",
    "input_guardrail",
    "human_in_the_loop"
  ]
}
```

Open `https://YOUR_SERVICE_URL/` in any browser to use TripMate AI.
