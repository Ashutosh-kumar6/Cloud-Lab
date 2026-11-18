# AI Cloud Lab

A cloud-based coding lab with AI-powered explanations, recommendations, and sandbox grading.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python 3.11) |
| Database | PostgreSQL 16 |
| Cache / Queue | Redis 7 |
| Scheduler | APScheduler (idle auto-cleanup) |
| Monitoring | Prometheus + Grafana (`prometheus-fastapi-instrumentator`) |
| AI | Google Gemini API (`google-genai`) |
| Grading | Docker-in-Docker sandbox |
| Auth | JWT (python-jose) + bcrypt |

---

## Running with Docker

### 1. Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- A [Google Gemini API key](https://aistudio.google.com/app/apikey)

### 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```
JWT_SECRET=<a random 32+ character string>
GEMINI_API_KEY=<your Gemini API key>
```

Generate a secure `JWT_SECRET`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Build and start all services

```bash
docker compose up --build
```

The API will be available at **http://localhost:8000**  
Interactive docs: **http://localhost:8000/docs**  
Prometheus UI: **http://localhost:9090**  
Grafana Dashboard: **http://localhost:3000** (credentials: `admin` / `admin`)

### 4. Stop services

```bash
docker compose down
```

To also remove the database volume (all data deleted):

```bash
docker compose down -v
```

---

## Running locally (without Docker)

### Prerequisites

- Python 3.11+
- PostgreSQL running on `localhost:5432`
- Redis running on `localhost:6379`

### Setup

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

Create `backend/.env` with your local connection strings (see `.env.example` for reference, but use `localhost` instead of `postgres`/`redis` as hostnames).

### Start the API

```bash
cd backend
uvicorn app.main:app --reload
```

---

## Running tests

```bash
cd backend
python -m pytest -v
```

---

## Applying database migrations

If Alembic is configured:

```bash
# Against a running Docker api service:
docker compose exec api alembic upgrade head

# Or locally:
cd backend && alembic upgrade head
```

---

## Enabling async Celery worker (optional)

The `worker` service in `docker-compose.yml` is commented out because grading currently runs synchronously.  
To enable it, uncomment the `worker` block in `docker-compose.yml` and restart:

```bash
docker compose up --build worker
```

---

## Idle Environment Auto-Stop

The backend includes a background scheduler (APScheduler) that runs every minute to inspect user activity tracked in Redis. Any user execution environment that has been idle for more than the configured timeout (default: 30 minutes) is automatically stopped and cleaned up.

Configure the timeout in `.env`:
```
IDLE_TIMEOUT_MINUTES=30
```

---

## Monitoring & Metrics

Prometheus scrapes metrics from the FastAPI `/metrics` endpoint every 10 seconds. Grafana is provisioned out-of-the-box with a pre-configured dashboard **AI Cloud Lab - Application & Custom Metrics**:

- **Request Rate**: HTTP requests per second broken down by handler
- **Latency p95**: 95th percentile request latency
- **Error Rate**: Percentage of requests returning 4xx or 5xx status codes
- **Submissions Graded**: Total submissions graded, segmented by status (`passed`, `failed`, `timeout`, `error`)
- **Submission Failures**: Counter of failed or erroneous code runs
- **Sandbox Timeouts**: Counter of code executions exceeding the execution time limit
- **Login Failures**: Counter of failed authentication attempts

Access Grafana at **http://localhost:3000** (default login `admin` / `admin`).

---

## Sandbox Runner Architecture & Security Analysis

### Docker Socket Access
When running inside Docker, the `api` service needs to launch untrusted student code containers. In `docker-compose.yml`, this is achieved by bind-mounting the host's Docker daemon socket:
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

### Security Implications
Mounting `/var/run/docker.sock` gives any process with access to the socket **root-equivalent control over the host system**:
1. **Host Compromise & Privilege Escalation**: A compromised container (or remote code execution vulnerability in the API) can make direct API calls to the Docker daemon to create privileged containers, mount the host's root filesystem (`/`), read/write host files, or modify system binaries.
2. **Container Escapes & Lateral Movement**: Access to the Docker socket effectively bypasses user namespace and cgroup boundaries, allowing arbitrary container inspection, execution, and termination.

### Safer Alternatives
To isolate untrusted execution environments without exposing the Docker socket:
1. **gVisor (`runsc`) / Kata Containers**:
   - Run untrusted student workloads with an application kernel emulator (`runsc`) that intercepts syscalls between the application and the host kernel, providing strong defense-in-depth against kernel exploits.
2. **Firecracker MicroVMs**:
   - Run each code execution inside a lightweight, ephemeral microVM with dedicated kernel and memory isolation that boots in under 100ms.
3. **Dedicated Remote Execution Service (Runner Worker)**:
   - Decouple the web API completely from Docker. The API pushes jobs to Redis/Celery; a separate, strictly sandboxed worker node located in an isolated VPC or host machine executes the containers and reports back over an authenticated, restricted gRPC/TLS interface.
4. **Rootless Docker / Podman**:
   - Run the container daemon in rootless mode so that even full daemon control only grants unprivileged user rights on the host system.

---

## Project Structure

```
ai-cloud-lab/
├── .env.example            # Environment variable template
├── docker-compose.yml      # Multi-service Docker orchestration
├── monitoring/
│   ├── prometheus/
│   │   └── prometheus.yml  # Prometheus scrape configuration
│   └── grafana/
│       ├── provisioning/   # Automated datasource & dashboard provisioning
│       └── dashboards/     # AI Cloud Lab pre-configured dashboard JSON
├── backend/
│   ├── Dockerfile          # API image (python:3.11-slim, non-root)
│   ├── requirements.txt
│   ├── storage/            # Uploaded files (mounted as a volume)
│   └── app/
│       ├── main.py
│       ├── api/v1/         # Route handlers
│       ├── core/           # Config, security, metrics, scheduler, deps
│       ├── db/             # SQLAlchemy engine & session
│       ├── models/         # ORM models
│       ├── schemas/        # Pydantic schemas
│       ├── services/       # Business logic
│       ├── runner/         # Sandbox grader + Celery
│       └── ai/             # Gemini explainer & rules
└── tests/                  # pytest suite
```
