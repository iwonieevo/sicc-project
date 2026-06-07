import { useEffect, useState } from "react";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "~/components/ui/card";
import { Navigate } from "react-router";
import { useAuth } from "~/providers/AuthProvider";
import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { formatParameterValue } from "~/lib/utils";
import { ListPagination } from "~/components/list-pagination";
import { secureFetch } from "~/lib/secure/secure-fetch";

interface CommandLog {
  queue_id: number;
  device_id: number;
  device_name: string;
  command_id: number;
  command_name: string;
  parameters?: Record<string, any>;
  status: "queued" | "running" | "done" | "error";
  result?: string;
  is_error?: boolean;
  queued_at?: string;
  started_at?: string;
  finished_at?: string;
}

export default function Page() {
  const { user, loading } = useAuth();
  const [logs, setLogs] = useState<CommandLog[]>([]);
  const [loadingLogs, setLoadingLogs] = useState(true);
  const [limit, setLimit] = useState(10);

  const fetchLogs = async (silent = false) => {
    if (!user) return;
    if (!silent) setLoadingLogs(true);
    try {
      const token = localStorage.getItem("accessToken");
      let url = `/api/logs?limit=${limit}`;
      if (limit === -1) {
        url = `/api/logs`;
      }
      const res = await secureFetch(url, {
        credentials: "include",
        headers: { Authorization: `Bearer ${token}` },
      });
      setLogs(res.ok ? await res.json<CommandLog[]>() : []);
    } catch (err) {
      console.error("Error fetching logs:", err);
      // setLogs([]);
    } finally {
      setLoadingLogs(false);
    }
  };

  useEffect(() => {
    fetchLogs();

    // fetch logs every 2 seconds to keep the view updated
    const interval = setInterval(() => fetchLogs(true), 2000);
    return () => clearInterval(interval);
  }, [user, limit]);

  if (loading) {
    return (
      <div className="flex items-center justify-center pt-16">
        <p>Loading...</p>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return null;
    return new Date(dateStr).toLocaleString();
  };

  return (
    <div className="h-full flex w-full items-start justify-center p-6 md:p-10">
      <div className="w-full max-w-4xl">
        <Card>
          <CardHeader>
            <CardTitle>Command Execution Logs</CardTitle>
            <CardDescription>View history of executed commands</CardDescription>
            <CardAction>
              {loadingLogs ? (
                <Button variant="link" className="text-foreground" disabled>
                  Loading...
                </Button>
              ) : (
                <Button variant="link" className="text-foreground" onClick={() => fetchLogs()}>
                  Reload
                </Button>
              )}
            </CardAction>
          </CardHeader>
          <CardContent>
            <ListPagination limit={limit} onLimitChange={setLimit} />
            <div className="space-y-3">
              {logs.map((log) => (
                <div key={log.queue_id} className="p-3 border-l-4">
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex flex-wrap gap-2">
                      <span className="font-semibold">Queue: {log.queue_id}</span>
                    </div>
                    <Badge variant={log.status}>
                      {log.status.toUpperCase()}
                    </Badge>
                  </div>
                  <div className="flex gap-4 mb-2">
                    <span className="text-sm text-gray-500">Device: <span className="font-semibold text-foreground">{log.device_name}</span></span>
                    <span className="text-sm text-gray-500">Command: <span className="font-semibold text-foreground">{log.command_name}</span></span>
                  </div>

                  {log.parameters && Object.keys(log.parameters).length > 0 && (

                    <><span>Body</span>
                      <div className="text-xs text-gray-400 mt-1 space-y-1 border-l-4 pl-2 mb-2">
                        {Object.entries(log.parameters).map(([key, value]) => (
                          <div key={key}>
                            <span className="font-medium text-gray-500">{key}:</span> {formatParameterValue(value)}
                          </div>
                        ))}
                      </div></>
                  )}

                  <div className="text-xs text-gray-400 space-x-4">
                    {log.queued_at && <span>Queued: {formatDate(log.queued_at)}</span>}
                    {log.started_at && <span>Started: {formatDate(log.started_at)}</span>}
                    {log.finished_at && <span>Finished: {formatDate(log.finished_at)}</span>}
                  </div>

                  {log.result && (
                    <div className="mt-2">
                      <strong className="text-sm">Result:</strong>
                      <pre className={`py-2 px-3 rounded mt-1 text-xs overflow-auto max-h-48 whitespace-pre-wrap wrap-break-word ${log.is_error ? 'text-red-400 border border-red-400' : 'text-green-400 bg-muted'
                        }`}>
                        {log.result}
                      </pre>
                    </div>
                  )}
                </div>
              ))}
              {logs.length === 0 && (
                <div className="text-center text-gray-500 py-8">
                  No execution logs yet
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
