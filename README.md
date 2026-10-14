# UptimeGuard Cloud
**Cloud-Based Website Uptime Monitoring and Intelligent Alert System**

UptimeGuard is a cloud-deployable web application that monitors public HTTP/HTTPS websites, records availability and response time, displays recent incidents, and calculates uptime from recorded checks.

## Features
- Dashboard with monitored website totals, current up/down state, response time, and 30-day recorded-check uptime
- Add, pause/resume, manually check, and delete monitored websites
- Scheduled checks every minute for enabled targets
- HTTP status, latency, error, and timestamp history
- Incident view and response-time chart
- FastAPI REST API and interactive Swagger docs at `/docs`
- Health endpoint at `/health`
- PostgreSQL support in cloud; SQLite fallback for local development
- URL validation that blocks private/internal targets and disables redirects

## Run locally
Python 3.11+ recommended.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```
Open http://127.0.0.1:8000

## Deploy on Render
1. Create a GitHub repository and upload this folder's files.
2. In Render, choose **New → Blueprint** and connect the repository containing `render.yaml`.
3. Review the web service and PostgreSQL database resources and deploy.
4. Open the generated public URL. Verify `/health` and `/docs`.
5. Add a public website to the dashboard and wait for monitoring results.

**Cost note:** Render's available plans and free-tier rules change. Check current pricing before provisioning a managed database. A persistent PostgreSQL database is recommended for a deployed demonstration; the local SQLite database is not suitable for ephemeral multi-instance production deployments.

## API endpoints
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Service health |
| GET | `/api/summary` | Dashboard metrics |
| GET | `/api/websites` | List monitored sites |
| POST | `/api/websites` | Add a site |
| POST | `/api/websites/{id}/check` | Run a manual check |
| PATCH | `/api/websites/{id}/toggle` | Pause/resume monitoring |
| DELETE | `/api/websites/{id}` | Delete a site and its history |
| GET | `/api/websites/{id}/history` | Retrieve recent check history |

## Cloud architecture
Browser → FastAPI application → PostgreSQL database
                         ↘ Background scheduler → public website endpoints

The included starter runs the scheduler inside the web process. For a production-grade multi-instance deployment, move the scheduler to a dedicated worker service and use a queue/lease mechanism so multiple instances do not duplicate checks. Add authentication, per-user authorization, alert delivery, rate limiting, retention policies, and monitoring before exposing this publicly.

## Uptime calculation
The displayed percentage is `successful recorded checks / all recorded checks × 100` over the last 30 days. It is based on observed checks, not a contractual SLA.

## Security notes
- Monitor only public sites you own or are authorized to test.
- The application blocks private, loopback, link-local, and reserved IPs at URL validation time and does not follow redirects.
- For a production deployment, enforce outbound network restrictions too, and revalidate DNS results at connection time to reduce DNS-rebinding risk.
- Add authentication and authorization before allowing public users to manage monitors.
- Do not put secrets in source control.

## Optional email alerts
Configure these environment variables on your host to send emails when a monitor changes from UP to DOWN or DOWN to UP:
- `SMTP_HOST`
- `SMTP_PORT` (usually `587`)
- `SMTP_USER`
- `SMTP_PASSWORD`
- `ALERT_EMAIL_FROM`
- `ALERT_EMAIL_TO`

Use your provider's SMTP credentials or an app password. Do not commit secrets to GitHub. Monitoring still works without SMTP configuration.
