#!/bin/sh
set -e

# This script runs during the first initialization of the Postgres container.
# It creates dedicated DB roles for backend and iot-server using environment variables.

# Connect explicitly to the initialized database (POSTGRES_DB) so psql does not
# attempt to connect to a database named after the OS user.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
DO \$\$
BEGIN
	IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_BACKEND_USER:-backend}') THEN
		CREATE ROLE ${DB_BACKEND_USER:-backend} LOGIN PASSWORD '${DB_BACKEND_PASSWORD:-backendpass}';
	END IF;
	IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_IOT_USER:-iot_server}') THEN
		CREATE ROLE ${DB_IOT_USER:-iot_server} LOGIN PASSWORD '${DB_IOT_PASSWORD:-iotpass}';
	END IF;
END
\$\$;
EOSQL
