# UptimeGuard Cloud
## Cloud-Based Website Uptime Monitoring and Intelligent Alert System

### Abstract
UptimeGuard Cloud is a web-based monitoring platform designed to improve visibility into website availability and performance. Users register public website URLs, after which the monitoring engine performs scheduled HTTP/HTTPS checks. The system stores timestamps, HTTP status codes, response latency, and error details in a database. A dashboard summarizes current availability, recorded uptime, response-time trends, and recent failures. The project demonstrates cloud application hosting, persistent storage, scheduled background processing, REST API design, fault detection, and operational observability.

### Problem statement
Website downtime can interrupt services, damage user trust, and create business losses. Manually checking websites is inefficient and cannot provide a useful historical record. A cloud-hosted monitoring system can automate periodic checks and make failures easier to investigate.

### Objectives
1. Automate periodic availability checks for registered websites.
2. Measure response latency and capture HTTP status codes and errors.
3. Maintain historical check records and calculate observed uptime.
4. Present results through a responsive dashboard and REST API.
5. Provide a deployable cloud architecture with persistent database storage.
6. Apply basic URL safety checks to prevent monitoring internal network targets.

### Proposed system
The user adds a website through the dashboard. FastAPI validates the URL and stores the monitor configuration. A background scheduler periodically retrieves enabled monitors and executes HTTP checks. Each result is written to the database. The frontend reads the API and refreshes metrics, website status, response-time charts, and recent incidents.

### Modules
- Website management: add, pause, resume, manually check, and delete targets.
- Monitoring engine: scheduled requests, timeout handling, status evaluation, and latency measurement.
- Data persistence: monitor configuration and timestamped results.
- Analytics: current status, average latency, and 30-day observed uptime.
- Dashboard: metrics, website table, history-derived incident list, and response-time chart.
- Operations: health endpoint, API documentation, logs, container configuration, and cloud deployment blueprint.

### Technology stack
Frontend: HTML, CSS, JavaScript, Chart.js.
Backend: Python, FastAPI, HTTPX.
Database: PostgreSQL in cloud deployments; SQLite for local development.
Scheduling: APScheduler starter implementation.
Deployment: Render Blueprint or Docker-compatible hosting.

### Architecture
Browser dashboard → FastAPI REST API → PostgreSQL.
The scheduled monitoring engine loads enabled monitors, checks public website endpoints, and stores each result. For production scaling, the scheduler should be deployed separately as a worker and coordinated through a task queue or lease mechanism.

### Functional requirements
- The system shall register valid public HTTP/HTTPS URLs.
- The system shall perform scheduled and manual checks.
- The system shall record availability, response time, status code, timestamp, and error information.
- The system shall calculate uptime from stored check results.
- The system shall show current status and recent failed checks, and optionally email on state transitions when SMTP is configured.
- The system shall support pause, resume, and delete operations.

### Non-functional requirements
- Responsive and understandable user interface.
- Persistent storage for deployment.
- Structured logs and a health endpoint.
- Request timeouts and basic URL validation.
- A design that can evolve to separate monitoring workers and horizontal scaling.

### Testing plan
1. Add a known public website and verify an initial check is stored.
2. Verify status code and response time appear on the dashboard.
3. Test an invalid URL and a private IP URL; the application should reject them.
4. Pause a monitor and verify scheduled checks skip it.
5. Run a manual check and confirm a new history record is created.
6. Delete a monitor and verify its history is removed.
7. Restart the service and verify records persist when PostgreSQL is configured.
8. Visit `/health` and `/docs` after deployment.
9. Simulate an unavailable authorized test endpoint and verify the failed check is recorded.

### Expected outcome
The completed starter application provides a single dashboard to manage public website monitors and review recorded availability and latency. Deploying it with PostgreSQL demonstrates cloud hosting and persistent data. Separating the worker, adding user authentication and email alerts, and implementing stronger network egress controls are recommended next steps for production use.

### Limitations
The starter version does not yet include user accounts, SMS alert delivery, true multi-region checks, a distributed task queue, or production-grade multi-tenant authorization. Optional email alerts are supported through SMTP environment variables. The scheduler runs within the web process, so it is intended for a single application instance until the worker architecture is separated. The uptime percentage reflects only recorded checks and should not be presented as an SLA guarantee.

### Conclusion
UptimeGuard Cloud demonstrates a practical application of cloud computing by combining web APIs, scheduled monitoring, persistent data, performance analytics, and deployment automation. The modular architecture provides a foundation for future enhancements such as alerting, multi-region monitoring, and horizontally scalable workers.
