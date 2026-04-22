GRANT USAGE                  ON SCHEMA public                   TO backend, iot_server;

-- sequences (needed for GENERATED ALWAYS AS IDENTITY inserts)
GRANT USAGE                  ON ALL SEQUENCES IN SCHEMA public  TO backend, iot_server;

-- users: backend manages auth, iot_server reads only
GRANT SELECT, INSERT, UPDATE ON TABLE public.users              TO backend;
GRANT SELECT                 ON TABLE public.users              TO iot_server;

-- devices: iot_server owns status updates, backend reads
GRANT SELECT, INSERT, UPDATE ON TABLE public.devices            TO iot_server;
GRANT SELECT                 ON TABLE public.devices            TO backend;

-- commands and parameters: backend manages definitions, iot_server reads
GRANT SELECT, INSERT, UPDATE ON TABLE public.commands           TO backend;
GRANT SELECT                 ON TABLE public.commands           TO iot_server;
GRANT SELECT, INSERT, UPDATE ON TABLE public.command_parameters TO backend;
GRANT SELECT                 ON TABLE public.command_parameters TO iot_server;

-- command lifecycle tables: iot_server writes, no direct backend access
GRANT SELECT, INSERT         ON TABLE public.command_queue      TO iot_server;
GRANT SELECT, INSERT         ON TABLE public.command_executions TO iot_server;
GRANT SELECT, INSERT         ON TABLE public.command_results    TO iot_server;

-- view: backend reads the aggregated lifecycle view only
GRANT SELECT                 ON TABLE public.v_command_log      TO backend, iot_server;

-- audit_log: neither service writes directly; backend reads for display
GRANT SELECT                 ON TABLE public.audit_log          TO backend;