#!/bin/sh
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${DB_IOT_USER:-iot_server};

GRANT SELECT ON TABLE command_logs TO ${DB_BACKEND_USER:-backend};
DO \$\$
BEGIN
	-- connect rights
	IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_BACKEND_USER:-backend}') THEN
		EXECUTE 'GRANT CONNECT ON DATABASE "' || current_database() || '" TO ${DB_BACKEND_USER:-backend}';
		EXECUTE 'GRANT USAGE ON SCHEMA public TO ${DB_BACKEND_USER:-backend}';
	END IF;
	IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_IOT_USER:-iot_server}') THEN
		EXECUTE 'GRANT CONNECT ON DATABASE "' || current_database() || '" TO ${DB_IOT_USER:-iot_server}';
		EXECUTE 'GRANT USAGE ON SCHEMA public TO ${DB_IOT_USER:-iot_server}';
	END IF;

	-- table grants (only if tables exist)
	IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='devices') THEN
		IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_BACKEND_USER:-backend}') THEN
			EXECUTE 'GRANT SELECT ON TABLE public.devices TO ${DB_BACKEND_USER:-backend}';
		END IF;
		IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_IOT_USER:-iot_server}') THEN
			EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE public.devices TO ${DB_IOT_USER:-iot_server}';
		END IF;
	END IF;

	-- users table grants
	IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='users') THEN
		IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_BACKEND_USER:-backend}') THEN
			EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE public.users TO ${DB_BACKEND_USER:-backend}';
		END IF;
		IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_IOT_USER:-iot_server}') THEN
			EXECUTE 'GRANT SELECT ON TABLE public.users TO ${DB_IOT_USER:-iot_server}';
		END IF;
	END IF;

	IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='command_logs') THEN
		IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_BACKEND_USER:-backend}') THEN
			EXECUTE 'GRANT SELECT ON TABLE public.command_logs TO ${DB_BACKEND_USER:-backend}';
		END IF;
		IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_IOT_USER:-iot_server}') THEN
			EXECUTE 'GRANT SELECT, INSERT, UPDATE ON TABLE public.command_logs TO ${DB_IOT_USER:-iot_server}';
		END IF;
	END IF;
END
\$\$;

-- IoT server: needs to insert/update logs and update device status
GRANT SELECT, INSERT, UPDATE ON TABLE command_logs TO ${DB_IOT_USER:-iot_server};
GRANT SELECT, INSERT, UPDATE ON TABLE devices TO ${DB_IOT_USER:-iot_server};
GRANT SELECT, INSERT, UPDATE ON TABLE users TO ${DB_BACKEND_USER:-backend};
GRANT SELECT ON TABLE users TO ${DB_IOT_USER:-iot_server};
EOSQL
