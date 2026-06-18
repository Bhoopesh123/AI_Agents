# Grafana Monitoring Agent

A small local SRE assistant with:

- Chat-style frontend on port `4005`
- Python backend on port `8005`
- Supervisor agent that routes user questions
- Grafana sub-agent that fetches health and metric data from Grafana
- Startup and stop scripts for Windows PowerShell and CMD

## Quick Start

```powershell
.\scripts\start.ps1
```

Open:

```text
http://localhost:4005
```

Stop:

```powershell
.\scripts\stop.ps1
```

## Grafana Configuration

The backend reads Grafana settings from `.env` in the project root. Fill in:

```text
GRAFANA_URL=https://your-grafana.example.com
GRAFANA_API_KEY=glsa_...
GRAFANA_DATASOURCE_UID=prometheus
```

Optional:

```text
GRAFANA_ORG_ID=1
GRAFANA_VERIFY_SSL=true
GRAFANA_TIMEOUT_SECONDS=20
```

Shell environment variables still work and take priority over `.env` values.

If Grafana variables are not set, the agent still runs and returns setup guidance plus backend health.

## API

Backend health:

```text
GET http://localhost:8005/api/health
```

Chat:

```text
POST http://localhost:8005/api/chat
```

Request body:

```json
{
  "message": "show cpu health for last 1h"
}
```

## Example Questions

- `Check Grafana health`
- `Show CPU health for last 1h`
- `Memory status for production`
- `Any failing instances?`
- `Run query up for last 30m`
