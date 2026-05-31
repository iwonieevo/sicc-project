#!/bin/sh
docker compose -f docker-compose.infra.yml down
python3 scripts/agents.py down --all
docker compose -f docker-compose.infra.yml up -d --build
python3 scripts/agents.py start agent-alpha agent-beta agent-gamma