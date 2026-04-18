import { useEffect, useState } from "react"

export default function Page() {
    const [logs, setLogs] = useState<any[]>([])

    useEffect(() => {
        fetch('/api/commands')
            .then(r => r.json())
            .then(data => setLogs(data))
            .catch(() => setLogs([]))
    }, [])

    return (
        <div className="h-full flex w-full items-center justify-center p-6 md:p-10">
            <div className="w-full max-w-3xl">
                <h2 className="text-2xl font-bold mb-4">Command Logs</h2>
                <div className="space-y-3">
                    {logs.map((l) => (
                        <div key={l.command_id} className="p-3 border rounded">
                            <div><strong>Command ID:</strong> {l.command_id}</div>
                            <div><strong>Device:</strong> {l.device_id}</div>
                            <div><strong>Status:</strong> {l.status}</div>
                            <div><strong>Result:</strong> <pre className="whitespace-pre-wrap">{l.result}</pre></div>
                            <div className="text-sm text-muted">{l.created_at}</div>
                        </div>
                    ))}
                    {logs.length === 0 && (
                        <div className="text-center text-sm text-muted">No logs yet</div>
                    )}
                </div>
            </div>
        </div>
    )
}
