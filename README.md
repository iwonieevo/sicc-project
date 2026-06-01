# SICC - Secure IoT Control Center

Distributed system for remote command execution on IoT agents via a web interface.

## Prerequisites

- Docker
- Docker Compose v2
- Python 3.11+ (for agent management script)
- OpenSSL (for generating database TLS certificates)

---

## Configuration

Copy and fill in the example environment files before starting anything:

```bash
cp .env.example .env
cp env/.env.agent.example env/.env.agent
cp env/.env.backend.example env/.env.backend
cp env/.env.server-iot.example env/.env.server-iot
```

### `.env`

| Variable                  | Default           | Description                                        |
| ------------------------- | ----------------- | -------------------------------------------------- |
| `FRONTEND_EXPOSED_PORT`   | `3000`            | Host port for the frontend                         |
| `BACKEND_EXPOSED_PORT`    | `8000`            | Host port for the backend                          |
| `IOT_SERVER_EXPOSED_PORT` | `7000`            | Host port for the IoT server                       |
| `POSTGRES_EXPOSED_PORT`   | `5432`            | Host port for PostgreSQL                           |
| `AGENT_NET_NAME`          | `sicc-agent-net`  | Docker network shared between infra and agents     |
| `AGENT_LABEL`             | `sicc.role=agent` | Label applied to agent containers                  |
| `POSTGRES_DB`             | `sicc`            | Database name                                      |
| `POSTGRES_USER`           | `admin`           | Postgres superuser name                            |
| `POSTGRES_PASSWORD`       | `changeme`        | Postgres superuser password                        |
| `DB_BACKEND_PASSWORD`     | `changeme`        | DB password for the backend service                |
| `DB_IOT_PASSWORD`         | `changeme`        | DB password for the IoT server                     |
| `ENV`                     | `development`     | Runtime environment (`development` / `production`) |

### `env/.env.agent`

| Variable                        | Default      | Description                                     |
| ------------------------------- | ------------ | ----------------------------------------------- |
| `POLL_INTERVAL`                 | `2`          | Seconds between command polls to the IoT server |
| `REGISTRATION_ATTEMPTS`         | `10`         | Number of registration retries on startup       |
| `SICC_TRUSTED_PUBLIC_KEYS_JSON` | `{}`         | Common trusted service public keys for agents   |
| `SICC_IOT_SERVER_IDENTITY`      | `iot-server` | Expected IoT server service identity            |
| `SICC_IOT_SERVER_KEY_ID`        | empty        | IoT server public key id used by agents         |
| `SICC_MAX_SKEW_MS`              | `30000`      | Maximum secure-message timestamp skew           |

Per-agent identity keys should not be stored in the shared `env/.env.agent` file.
Place them in a private env file and pass that path to `scripts/agents.py start`.
Files under `env/agents/` are ignored by git.

### `env/.env.backend`

| Variable                          | Default    | Description               |
| --------------------------------- | ---------- | ------------------------- |
| `JWT_SECRET_KEY`                  | `changeme` | Secret used to sign JWTs  |
| `JWT_ALGORITHM`                   | `HS256`    | JWT signing algorithm     |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30`       | Token lifetime in minutes |

### `env/.env.server-iot`

| Variable                          | Default | Description                                                   |
| --------------------------------- | ------- | ------------------------------------------------------------- |
| `DEVICE_MONITOR_INTERVAL_SECONDS` | `15`    | Seconds between health checks to mark inactive agents offline |

---

## TLS Certificates

OpenSSL must be available on your PATH. On Linux/macOS:

```bash
sh scripts/generate-db-certs.sh
```

On Windows with Git Bash (recommended, bundles OpenSSL):

```bash
MSYS_NO_PATHCONV=1 sh scripts/generate-db-certs.sh
```

Or with PowerShell if OpenSSL is on your PATH:

```powershell
.\scripts\generate-db-certs.ps1
```

This creates a local CA and a PostgreSQL server certificate under `db/certs/`. The script refuses to overwrite existing certificates - delete the files in `db/certs/` first if you need to regenerate them.

---

## Running the Project

### Infrastructure

Infrastructure must be running before any agents are started.

```bash
docker compose -f docker-compose.infra.yml up -d --build
```

Services started: `frontend`, `backend`, `iot-server`, `db`.

### Agents

Agents are managed via the `agents.py` script:

```bash
python scripts/agents.py start agent-alpha
python scripts/agents.py start agent-alpha env/agents/.env.alpha
python scripts/agents.py start agent-alpha agent-beta agent-gamma
python scripts/agents.py start agent-alpha env/agents/.env.alpha agent-beta env/agents/.env.beta
```

The agent name is arbitrary — any string matching `[a-zA-Z0-9][a-zA-Z0-9_.-]+` is valid.

When `SECURE_MODE=true`, each agent needs a private per-agent env file with its own
identity and Ed25519 key:

```env
SICC_SERVICE_IDENTITY=agent-alpha
SICC_SERVICE_KEY_ID=...
SICC_SERVICE_PRIVATE_KEY_B64=...
```

Generate these values with:

```bash
python scripts/generate-security-key.py
```

On first run, the agent container is created. On subsequent runs of the same name, the existing stopped container is resumed.

> Note: Changing an env file does not update an existing container.

---

## Stopping and Resetting

### Stop agents

Stop a specific agent (container is kept, can be resumed):

```bash
python scripts/agents.py stop agent-alpha
python scripts/agents.py stop agent-alpha agent-beta
python scripts/agents.py stop --all
```

### Remove agents

Stop and remove agent containers:

```bash
python scripts/agents.py down agent-alpha
python scripts/agents.py down --all
```

### Stop infrastructure

```bash
docker compose -f docker-compose.infra.yml stop
```

This preserves database data and container state. Subsequent starts are instant.

### Tear down infrastructure

Removes containers and networks, but keeps database volumes:

```bash
docker compose -f docker-compose.infra.yml down
```

### Full reset (destroys database)

Permanently deletes all data including the PostgreSQL volume:

```bash
docker compose -f docker-compose.infra.yml down -v
```

---

## Logs

### Infrastructure logs

All services:

```bash
docker compose -f docker-compose.infra.yml logs -f
```

Specific service:

```bash
docker compose -f docker-compose.infra.yml logs -f iot-server
docker compose -f docker-compose.infra.yml logs -f backend
```

### Agents logs

Specific agent:

```bash
python scripts/agents.py logs agent-alpha
python scripts/agents.py logs agent-alpha -f
```

---

## Agent Management Reference

```txt
python scripts/agents.py <command> [args]

Commands:
  start <name> [env_file] [name [env_file] ...]   Create or resume agent(s)
  stop  <name> [name ...]   Stop agent(s), keep containers  [--all]
  down  <name> [name ...]   Stop and remove agent(s)        [--all]
  logs  <name>              Show logs for one agent         [-f] [--tail N]
  list                      List running and stopped agents
```

---

## Access

Once running, services are available on the ports configured in `.env`:

- Frontend: [http://localhost:3000](http://localhost:3000) (`FRONTEND_EXPOSED_PORT`)
- Backend API: [http://localhost:8000](http://localhost:8000) (`BACKEND_EXPOSED_PORT`)
- IoT Server: [http://localhost:7000](http://localhost:7000) (`IOT_SERVER_EXPOSED_PORT`)

Create an account via the sign-up page, then log in to issue commands.
