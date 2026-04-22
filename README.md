# sicc-project (Minimal)

Secure IoT Control Center

Prerequisites
- Docker

Quick start (development)
```bash
docker compose up --build
```

To recreate the database (runs init scripts):
```bash
docker compose down --volumes
docker compose up --build
```

Run multiple agents (after stack is up):
```bash
docker compose up --scale agent=3 -d --build
```

Defaults (development)
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/api
- IoT Server: http://localhost:7000

Seeded users (dev):
- admin@example.com / admin
- iot-server@example.com / iot-server
- backend@example.com / backend

DB roles
- `POSTGRES_USER` / `POSTGRES_PASSWORD`: initial DB superuser used by the
	Postgres image during first initialization (configured in `.env`).
- `DB_BACKEND_USER` / `DB_BACKEND_PASSWORD`: backend app DB account.
- `DB_IOT_USER` / `DB_IOT_PASSWORD`: IoT server DB account.
