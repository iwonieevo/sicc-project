# SICC - Secure IoT Control Center

Distributed system for remote command execution on IoT agents via a web interface.

## Prerequisites

- Docker
- Docker Compose v2

---

## Configuration

Copy and fill in the example environment files before starting anything:

```bash
cp .env.example .env
cp env/.env.agent.example env/.env.agent
cp env/.env.backend.example env/.env.backend
```

### `.env` (root)

| Variable | Default | Description |
|---|---|---|
| `FRONTEND_EXPOSED_PORT` | `3000` | Host port exposed for the frontend |
| `BACKEND_EXPOSED_PORT` | `8000` | Host port exposed for the backend |
| `IOT_SERVER_EXPOSED_PORT` | `7000` | Host port exposed for the IoT server |
| `POSTGRES_EXPOSED_PORT` | `5432` | Host port exposed for PostgreSQL |
| `AGENT_NET_NAME` | `sicc-agent-net` | Docker network shared between infra and agents |
| `POSTGRES_DB` | `sicc` | Database name |
| `POSTGRES_USER` | `admin` | Postgres superuser name |
| `POSTGRES_PASSWORD` | | Postgres superuser password (required) |
| `DB_BACKEND_PASSWORD` | | DB password for the backend service (required) |
| `DB_IOT_PASSWORD` | | DB password for the IoT server (required) |
| `ENV` | `development` | Runtime environment (`development` / `production`) |

### `env/.env.agent`

| Variable | Default | Description |
|---|---|---|
| `POLL_INTERVAL` | `2` | Seconds between command polls to the IoT server |
| `REGISTRATION_ATTEMPTS` | `10` | Number of registration retries on startup |

### `env/.env.backend`

| Variable | Default | Description |
|---|---|---|
| `JWT_SECRET_KEY` | | Secret used to sign JWTs (change in production) |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Token lifetime in minutes |

---

## Running the Project

### Start everything at once

```bash
docker-compose -f docker-compose.infra.yml -f docker-compose.agents.yml --profile all up -d --build
```

### Start infrastructure only

```bash
docker-compose -f docker-compose.infra.yml up -d --build
```

### Start agents only (infrastructure must already be running)

All agents:
```bash
docker-compose -f docker-compose.agents.yml --profile all up -d
```

Specific agents:
```bash
docker-compose -f docker-compose.agents.yml --profile alpha --profile beta up -d
```

---

## Stopping the Project

### Stop everything

```bash
docker-compose -f docker-compose.infra.yml -f docker-compose.agents.yml --profile all down
```

### Stop infrastructure only

```bash
docker-compose -f docker-compose.infra.yml down
```

### Stop all agents (leave infrastructure running)

```bash
docker-compose -f docker-compose.agents.yml --profile all down
```

### Stop a specific agent

```bash
docker-compose -f docker-compose.agents.yml --profile alpha down
# or directly:
docker stop agent-alpha && docker rm agent-alpha
```

---

## Resetting the Database

Bring everything down and remove the volume:

```bash
docker-compose -f docker-compose.infra.yml down -v
```

Then start again:

```bash
docker-compose -f docker-compose.infra.yml up -d --build
```

---

## Logs

```bash
# All infrastructure services
docker-compose -f docker-compose.infra.yml logs -f

# Specific infrastructure service
docker-compose -f docker-compose.infra.yml logs -f iot-server
docker-compose -f docker-compose.infra.yml logs -f backend

# All agents
docker-compose -f docker-compose.agents.yml --profile all logs -f

# Specific agent
docker logs -f agent-alpha
```

---

## Managing Agents

### Predefined agents

The following named agents are defined in `docker-compose.agents.yml`, each with its own Docker Compose profile:

| Agent | Profile |
|---|---|
| `agent-alpha` | `alpha` |
| `agent-beta` | `beta` |
| `agent-gamma` | `gamma` |
| `agent-delta` | `delta` |
| `agent-epsilon` | `epsilon` |

Use `--profile all` to start all of them at once.

### Adding a named agent

Add a new service to `docker-compose.agents.yml`:

```yaml
agent-zeta:
  <<: *agent-base
  container_name: agent-zeta
  environment:
    - AGENT_NAME=agent-zeta
  profiles: ["zeta", "all"]
```

Then start it:

```bash
docker-compose -f docker-compose.agents.yml --profile zeta up -d
```

### Scaling agents dynamically

For anonymous agents, use the base `agent` service with `--scale`. It has the `never` profile to prevent accidental standalone use:

```bash
docker-compose -f docker-compose.agents.yml --profile never up -d --scale agent=5
```

Each container falls back to its Docker hostname as the agent name since no `AGENT_NAME` is set:

```python
agent_name = os.getenv("AGENT_NAME", socket.gethostname())
```

---

## Access

Once running, services are available on the ports configured in `.env`:

- Frontend (`FRONTEND_EXPOSED_PORT`) - default http://localhost:3000
- Backend API (`BACKEND_EXPOSED_PORT`) - default http://localhost:8000
- IoT Server (`IOT_SERVER_EXPOSED_PORT`) - default http://localhost:7000

Create an account via the sign-up page, then log in to issue commands.