# TripMate AI - Cloud Run Deployment Script (Mumbai: asia-south1)
$ErrorActionPreference = "Stop"

$Region = "asia-south1"
$ServiceName = "tripmate-ai"
$TempEnvYaml = Join-Path $PSScriptRoot ".env.cloudrun.yaml"

Write-Host "==> Checking gcloud setup..." -ForegroundColor Cyan
$Project = gcloud config get-value project 2>$null
if (-not $Project) {
    Write-Error "No active gcloud project found. Please run 'gcloud config set project <PROJECT_ID>'."
}
Write-Host "Target Project: $Project" -ForegroundColor Green
Write-Host "Target Region:  $Region (Mumbai)" -ForegroundColor Green

# Ensure .env exists
$EnvFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Error ".env file not found in $PSScriptRoot"
}

Write-Host "==> Generating clean Cloud Run environment configuration from .env..." -ForegroundColor Cyan
python -c @"
import json
from dotenv import dotenv_values

envs = dotenv_values()
needed = [
    'DATABASE_URL',
    'GROQ_API_KEY',
    'TAVILY_API_KEY',
    'OPENWEATHER_API_KEY',
    'AVIATIONSTACK_API_KEY',
    'DEFAULT_ORIGIN_IATA',
    'GROQ_MODEL',
]

out = {k: v.strip() for k, v in envs.items() if k in needed and v}
if 'GROQ_MODEL' not in out:
    out['GROQ_MODEL'] = 'openai/gpt-oss-120b'

if 'AVIATIONSTACK_API_KEY' in out and 'AVIATION_STACK_API_KEY' not in out:
    out['AVIATION_STACK_API_KEY'] = out['AVIATIONSTACK_API_KEY']

lines = [f'{k}: {json.dumps(v)}\n' for k, v in out.items()]
with open(r'$TempEnvYaml', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print(f'Prepared {len(out)} environment variables successfully.')
"@

if (-not (Test-Path $TempEnvYaml)) {
    Write-Error "Failed to generate $TempEnvYaml."
}

try {
    Write-Host "==> Deploying $ServiceName to Google Cloud Run ($Region)..." -ForegroundColor Cyan
    gcloud run deploy $ServiceName `
        --source . `
        --region $Region `
        --platform managed `
        --allow-unauthenticated `
        --memory 1Gi `
        --cpu 1 `
        --timeout 300 `
        --env-vars-file $TempEnvYaml

    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n Deployment to Cloud Run ($Region) complete!" -ForegroundColor Green
    } else {
        Write-Error "Deployment failed with exit code $LASTEXITCODE"
    }
}
finally {
    if (Test-Path $TempEnvYaml) {
        Remove-Item -Force $TempEnvYaml
        Write-Host "Cleaned up temporary environment file." -ForegroundColor DarkGray
    }
}
