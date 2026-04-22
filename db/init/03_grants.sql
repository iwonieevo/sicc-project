GRANT USAGE                  ON SCHEMA public                   TO backend, iot_server;
GRANT USAGE                  ON ALL SEQUENCES IN SCHEMA public  TO backend, iot_server;

GRANT SELECT, INSERT, UPDATE ON TABLE public.users              TO backend;
GRANT SELECT                 ON TABLE public.users              TO iot_server;

GRANT SELECT, INSERT, UPDATE ON TABLE public.devices            TO iot_server;
GRANT SELECT                 ON TABLE public.devices            TO backend;

GRANT SELECT, INSERT, UPDATE ON TABLE public.commands           TO backend;
GRANT SELECT                 ON TABLE public.commands           TO iot_server;
GRANT SELECT, INSERT, UPDATE ON TABLE public.command_parameters TO backend;
GRANT SELECT                 ON TABLE public.command_parameters TO iot_server;

GRANT SELECT, INSERT         ON TABLE public.command_queue      TO iot_server;
GRANT SELECT, INSERT         ON TABLE public.command_executions TO iot_server;
GRANT SELECT, INSERT         ON TABLE public.command_results    TO iot_server;

GRANT SELECT                 ON TABLE public.v_command_log      TO backend, iot_server;
GRANT SELECT                 ON TABLE public.audit_log          TO backend;