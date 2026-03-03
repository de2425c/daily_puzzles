# Daily Puzzles

Poker puzzle generation system using Deepsolver API for GTO simulations.

## Architecture

- **admin-ui/**: Vue.js admin interface for creating and managing daily puzzles (Vite)
- **api/**: FastAPI backend (Python)
- **deepsolver/**: Client library for Deepsolver GTO solver API
- **storage/**: Data models and Firebase integration

## Deployment

### Cloud Run (API)

The API is deployed to Google Cloud Run:
- Service: `daily-puzzles-api`
- Region: `us-central1`
- URL: https://daily-puzzles-api-70941987896.us-central1.run.app

### Required Environment Variables (Cloud Run)

```bash
# View current env vars
gcloud run services describe daily-puzzles-api --region=us-central1 --format="yaml(spec.template.spec.containers[0].env)"

# Update env vars
gcloud run services update daily-puzzles-api --region=us-central1 --update-env-vars="DEEPSOLVER_API_TOKEN=<token>"
```

| Variable | Description |
|----------|-------------|
| `DEEPSOLVER_API_TOKEN` | API token for Deepsolver GTO solver |
| `ANTHROPIC_API_KEY` | API key for Claude (puzzle generation) |
| `CORS_ORIGINS` | Allowed CORS origins |

### Admin UI (Vercel)

The admin UI is deployed to Vercel. It connects to the Cloud Run API.

Configure `VITE_API_URL` in admin-ui to point to the Cloud Run URL.

## Local Development

```bash
# API (from daily_puzzles/)
source .venv/bin/activate
uvicorn api.main:app --reload --port 8000

# Admin UI (from admin-ui/)
npm run dev
```

Local `.env` file (daily_puzzles/.env):
```
DEEPSOLVER_API_TOKEN=<token>
ANTHROPIC_API_KEY=<key>
```

## Common Issues

### "DEEPSOLVER_API_TOKEN not set" error in admin UI

The Cloud Run service is missing the environment variable. Fix:
```bash
gcloud run services update daily-puzzles-api --region=us-central1 --update-env-vars="DEEPSOLVER_API_TOKEN=<token>"
```
