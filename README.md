# README.md

```markdown
# SICC - Secure IoT Control Center

Distributed system for remote command execution on IoT agents with secure communication, role-based access control, and comprehensive audit logging.

## Prerequisites

- Docker
- Docker Compose v2
- Git (optional)

## Architecture Overview

### Components

| Service | Technology | Port | Description |
|---------|------------|------|-------------|
| Frontend | React + Vite + shadcn/ui | 3000 | Web UI for user interaction |
| Backend | FastAPI (Python) | 8000 | Auth, command management, API gateway |
| IoT Server | FastAPI (Python) | 7000 | Agent orchestration, command queuing |
| Agent | Python | - | Edge device simulator, executes commands |
| Database | PostgreSQL 16 | 5432 | Persistent storage |

### Database Schema

**Core Tables**
- `users` - Web authentication, passwords hashed
- `devices` - Agent registry with status tracking
- `commands` - Available command definitions (Python code)
- `command_parameters` - Parameter metadata for commands

**Lifecycle Tables** (IoT Server only)
- `command_queue` - Commands awaiting execution
- `command_executions` - Commands currently running
- `command_results` - Completed command results

**Views**
- `v_command_log` - Unified command lifecycle status

**Audit**
- `audit_log` - Immutable change tracking (triggers on config tables)

### Command Lifecycle States

| State | Description |
|-------|-------------|
| `queued` | In command_queue only |
| `running` | In command_queue + command_executions |
| `done` | All three tables, is_error = FALSE |
| `error` | All three tables, is_error = TRUE |

## Environment Variables

### .env (root)

| Variable | Default | Description |
|----------|---------|-------------|
| `FRONTEND_PORT` | 3000 | Frontend exposed port |
| `BACKEND_PORT` | 8000 | Backend API port |
| `IOT_SERVER_PORT` | 7000 | IoT Server port |
| `AGENT_NET_NAME` | sicc-agent-net | Docker network name for agents |
| `POSTGRES_DB` | sicc | Database name |
| `POSTGRES_HOST` | db | Database host |
| `POSTGRES_USER` | admin | Postgres superuser |
| `POSTGRES_PASSWORD` | - | Postgres superuser password |
| `DB_BACKEND_USER` | backend | Backend service DB user |
| `DB_BACKEND_PASSWORD` | - | Backend service DB password |
| `DB_IOT_USER` | iot_server | IoT Server DB user |
| `DB_IOT_PASSWORD` | - | IoT Server DB password |

### env/.env.backend

| Variable | Description |
|----------|-------------|
| `JWT_SECRET_KEY` | Secret for JWT signing (change in production) |
| `JWT_ALGORITHM` | JWT algorithm (HS256) |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Token expiration time |

### env/.env.agent

| Variable | Default | Description |
|----------|---------|-------------|
| `POLL_INTERVAL` | 2 | Seconds between command polls |
| `IOT_SERVER_URL` | http://iot-server:7000 | IoT Server URL |

### env/.env.frontend

| Variable | Description |
|----------|-------------|
| `CHOKIDAR_USEPOLLING` | Enable polling for file changes in Docker |

## Getting Started

### 1. Clone and Configure

```bash
git clone <repository-url>
cd sicc-project
cp .env.example .env
# Edit .env with your values (passwords, keys, etc.)
```

### 2. Start Infrastructure

```bash
docker-compose -f docker-compose.infra.yml up -d
```

This starts: frontend, backend, iot-server, and database.

Verify:
```bash
docker-compose -f docker-compose.infra.yml ps
```

### 3. Start Agents

Start all predefined agents:
```bash
docker-compose -f docker-compose.agents.yml --profile all up -d
```

Start specific agents:
```bash
docker-compose -f docker-compose.agents.yml --profile alpha --profile beta up -d
```

Start everything together:
```bash
docker-compose -f docker-compose.infra.yml -f docker-compose.agents.yml --profile all up -d
```

### 4. Access the Application

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- IoT Server: http://localhost:7000

Create an account via the signup page, then log in.

## Managing Agents

### Adding a New Agent

Edit `docker-compose.agents.yml` and add a new service:

```yaml
agent-zeta:
  <<: *agent-base
  container_name: agent-zeta
  environment:
    - AGENT_NAME=agent-zeta
  profiles: ["zeta", "all"]
```

Start it:
```bash
docker-compose -f docker-compose.agents.yml --profile zeta up -d
```

### Stopping Agents

Stop all agents (infrastructure keeps running):
```bash
docker-compose -f docker-compose.agents.yml --profile all down
```

Stop specific agent:
```bash
docker stop agent-alpha && docker rm agent-alpha
```

### Viewing Logs

Infrastructure logs:
```bash
docker-compose -f docker-compose.infra.yml logs -f
```

All agents logs:
```bash
docker-compose -f docker-compose.agents.yml --profile all logs -f
```

Specific service logs:
```bash
docker-compose -f docker-compose.infra.yml logs -f backend
docker logs -f agent-alpha
```

## Development

### Rebuilding After Code Changes

```bash
docker-compose -f docker-compose.infra.yml build --no-cache
docker-compose -f docker-compose.agents.yml build --no-cache
```

### Database Reset

```bash
docker-compose -f docker-compose.infra.yml down -v
docker-compose -f docker-compose.infra.yml up -d
```

## Stopping Everything

```bash
docker-compose -f docker-compose.infra.yml -f docker-compose.agents.yml --profile all down
```

To also remove volumes (database data):
```bash
docker-compose -f docker-compose.infra.yml -f docker-compose.agents.yml --profile all down -v
```

## Security Notes

- Change `JWT_SECRET_KEY` and database passwords in production
- Use HTTPS in production (not configured in development)
- The system uses soft deletes (`is_deleted` flag) - no data is permanently removed
- Audit log tracks all configuration changes automatically