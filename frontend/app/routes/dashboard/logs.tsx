import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Navigate } from "react-router";
import { useAuth } from "~/providers/AuthProvider";

interface CommandLog {
  queue_id: number;
  device_id: number;
  command_id: number;
  parameters?: Record<string, any>;
  status: string;
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

  useEffect(() => {
    if (!user) return;
    
    const token = localStorage.getItem("accessToken");
    fetch('/api/logs', {
      credentials: "include",
      headers: { "Authorization": `Bearer ${token}` }
    })
      .then(res => res.ok ? res.json() : [])
      .then(data => {
        console.log("Logs loaded:", data);
        setLogs(data);
      })
      .catch(err => {
        console.error("Failed to fetch logs:", err);
        setLogs([]);
      })
      .finally(() => setLoadingLogs(false));
  }, [user]);

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

  if (loadingLogs) {
    return (
      <div className="h-full flex items-center justify-center">
        <p>Loading logs...</p>
      </div>
    );
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'queued': return 'text-yellow-600';
      case 'running': return 'text-blue-600';
      case 'done': return 'text-green-600';
      case 'error': return 'text-red-600';
      default: return 'text-gray-600';
    }
  };

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
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {logs.map((log) => (
                <div key={log.queue_id} className="p-3 border rounded-lg">
                  <div className="flex justify-between items-start mb-2">
                    <div className="flex flex-wrap gap-2">
                      <span className="font-semibold">Queue: {log.queue_id}</span>
                      <span className="text-sm text-gray-500">Device: {log.device_id}</span>
                      <span className="text-sm text-gray-500">Command: {log.command_id}</span>
                    </div>
                    <span className={`font-medium ${getStatusColor(log.status)}`}>
                      {log.status}
                    </span>
                  </div>
                  
                  {log.parameters && Object.keys(log.parameters).length > 0 && (
                    <div className="text-xs text-gray-500 mb-2">
                      Parameters: {JSON.stringify(log.parameters)}
                    </div>
                  )}
                  
                  <div className="text-xs text-gray-400 space-x-4">
                    {log.queued_at && <span>Queued: {formatDate(log.queued_at)}</span>}
                    {log.started_at && <span>Started: {formatDate(log.started_at)}</span>}
                    {log.finished_at && <span>Finished: {formatDate(log.finished_at)}</span>}
                  </div>
                  
                  {log.result && (
                      <div className="mt-2">
                          <strong className="text-sm">Result:</strong>
                          <pre className={`p-2 rounded mt-1 text-xs overflow-auto max-h-48 whitespace-pre-wrap break-words ${
                              log.is_error ? 'text-red-800 border border-red-200' : 'text-green-800 border border-gray-200'
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