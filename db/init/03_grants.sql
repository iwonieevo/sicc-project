-- Schema access
GRANT USAGE ON SCHEMA public TO backend, iot_server;

-- users table: backend manages auth, iot_server only reads
GRANT SELECT, INSERT, UPDATE ON TABLE public.users TO backend;
GRANT SELECT                 ON TABLE public.users TO iot_server;

-- devices table: iot_server owns it, backend reads
GRANT SELECT, INSERT, UPDATE ON TABLE public.devices TO iot_server;
GRANT SELECT                 ON TABLE public.devices TO backend;

-- command_logs: iot_server writes, backend reads
GRANT SELECT, INSERT, UPDATE ON TABLE public.command_logs TO iot_server;
GRANT SELECT                 ON TABLE public.command_logs TO backend;