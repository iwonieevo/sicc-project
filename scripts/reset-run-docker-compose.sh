#!/bin/sh
docker compose -f docker-compose.infra.yml down
docker compose -f docker-compose.agents.yml --profile all down
docker compose -f docker-compose.infra.yml up -d --build
docker compose -f docker-compose.agents.yml --profile all up -d --build