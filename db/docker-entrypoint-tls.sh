#!/bin/sh
set -e

TLS_SOURCE_DIR="${POSTGRES_TLS_SOURCE_DIR:-/run/secrets/postgres-tls}"
TLS_TARGET_DIR="${POSTGRES_TLS_TARGET_DIR:-/var/lib/postgresql/tls}"

missing_files=""

for file in "$TLS_SOURCE_DIR/server.crt" "$TLS_SOURCE_DIR/server.key"; do
  if [ -d "$file" ]; then
    missing_files="$missing_files
  - $file is a directory; remove the matching host path under db/certs/ and regenerate certificates"
    continue
  fi

  if [ ! -s "$file" ]; then
    missing_files="$missing_files
  - $file"
  fi
done

if [ -n "$missing_files" ]; then
  cat >&2 <<EOF
Database TLS certificates are missing, empty, or invalid:
$missing_files

Generate local development certificates before starting the project:
  sh scripts/generate-db-certs.sh

On Windows:
  .\\scripts\\generate-db-certs.ps1

The generated files are stored under db/certs/ and are intentionally ignored by Git.
EOF
  exit 1
fi

mkdir -p "$TLS_TARGET_DIR"
cp "$TLS_SOURCE_DIR/server.crt" "$TLS_TARGET_DIR/server.crt"
cp "$TLS_SOURCE_DIR/server.key" "$TLS_TARGET_DIR/server.key"
chown postgres:postgres "$TLS_TARGET_DIR/server.crt" "$TLS_TARGET_DIR/server.key"
chmod 644 "$TLS_TARGET_DIR/server.crt"
chmod 600 "$TLS_TARGET_DIR/server.key"

exec /usr/local/bin/docker-entrypoint.sh "$@"
