#!/bin/sh
set -e

TLS_SOURCE_DIR="${POSTGRES_TLS_SOURCE_DIR:-/run/secrets/postgres-tls}"
TLS_TARGET_DIR="${POSTGRES_TLS_TARGET_DIR:-/var/lib/postgresql/tls}"

if [ -f "$TLS_SOURCE_DIR/server.crt" ] && [ -f "$TLS_SOURCE_DIR/server.key" ]; then
  mkdir -p "$TLS_TARGET_DIR"
  cp "$TLS_SOURCE_DIR/server.crt" "$TLS_TARGET_DIR/server.crt"
  cp "$TLS_SOURCE_DIR/server.key" "$TLS_TARGET_DIR/server.key"
  chown postgres:postgres "$TLS_TARGET_DIR/server.crt" "$TLS_TARGET_DIR/server.key"
  chmod 644 "$TLS_TARGET_DIR/server.crt"
  chmod 600 "$TLS_TARGET_DIR/server.key"
fi

exec /usr/local/bin/docker-entrypoint.sh "$@"
