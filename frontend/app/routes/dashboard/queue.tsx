import { useEffect, useState } from "react";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Navigate } from "react-router";
import { useAuth } from "~/providers/AuthProvider";
import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { formatParameterValue } from "~/lib/utils";

interface Device {
    id: number;
    name: string;
    ip_address: string;
    status: string;
}

interface QueueItem {
    queue_id: number;
    device_id: number;
    command_id: number;
    command_name: string;
    status: string;
    queued_at: string;
    parameters?: Record<string, any>;
}

export default function QueuePage() {
    const { user, loading } = useAuth();
    const [devices, setDevices] = useState<Device[]>([]);
    const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(null);
    const [queueItems, setQueueItems] = useState<QueueItem[]>([]);
    const [loadingData, setLoadingData] = useState(true);
    const [sortOrder, setSortOrder] = useState<'newest' | 'oldest'>('oldest');

    useEffect(() => {
        if (!user) return;
        const fetchDevices = async () => {
            try {
                const token = localStorage.getItem("accessToken");
                const res = await fetch('/api/devices', {
                    headers: { "Authorization": `Bearer ${token}` }
                });
                if (res.ok) {
                    const data = await res.json();
                    setDevices(data);
                    if (data.length > 0 && selectedDeviceId === null) {
                        setSelectedDeviceId(data[0].id);
                    }
                }
            } catch (err) {
                console.error(err);
            } finally {
                setLoadingData(false);
            }
        };
        fetchDevices();
    }, [user]);

    const fetchQueue = async (silent = false) => {
        if (!selectedDeviceId || !user) return;
        if (!silent) setLoadingData(true);
        try {
            const token = localStorage.getItem("accessToken");
            const res = await fetch(`/api/devices/${selectedDeviceId}/queue`, {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setQueueItems(data);
            }
        } catch (err) {
            console.error(err);
        } finally {
            setLoadingData(false);
        }
    };

    useEffect(() => {
        fetchQueue();
        const interval = setInterval(() => fetchQueue(true), 2000);
        return () => clearInterval(interval);
    }, [selectedDeviceId, user]);

    const handleCancel = async (queueId: number) => {
        if (!selectedDeviceId) return;
        try {
            const token = localStorage.getItem("accessToken");
            const res = await fetch(`/api/devices/${selectedDeviceId}/queue/${queueId}/cancel`, {
                method: 'POST',
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (res.ok) {
                fetchQueue();
            }
        } catch (err) {
            console.error(err);
        }
    };

    if (loading) return <div className="flex items-center justify-center pt-16"><p>Loading...</p></div>;
    if (!user) return <Navigate to="/login" replace />;

    return (
        <div className="h-full flex w-full items-start justify-center p-6 md:p-10">
            <div className="w-full max-w-4xl space-y-6">
                <Card>
                    <CardHeader>
                        <CardTitle>Device Queue Management</CardTitle>
                        <CardDescription>Select a device to view and manage its queue</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="flex gap-2 flex-wrap">
                            {devices.map(d => (
                                <Button
                                    key={d.id}
                                    variant={selectedDeviceId === d.id ? "default" : "outline"}
                                    onClick={() => setSelectedDeviceId(d.id)}
                                >
                                    {d.name}
                                </Button>
                            ))}
                            {devices.length === 0 && !loadingData && (
                                <p className="text-sm text-muted-foreground">No devices found.</p>
                            )}
                        </div>
                    </CardContent>
                </Card>

                {selectedDeviceId && (
                    <Card>
                        <CardHeader>
                            <CardTitle>Queued Commands</CardTitle>
                            <CardDescription>Commands waiting to be executed on this device</CardDescription>
                            <CardAction className="flex gap-2 items-center">
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => setSortOrder(prev => prev === 'newest' ? 'oldest' : 'newest')}
                                >
                                    Sort: {sortOrder === 'newest' ? 'Newest' : 'Oldest'} First
                                </Button>
                                <Button variant="link" onClick={() => fetchQueue()}>Refresh</Button>
                            </CardAction>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-3">
                                {queueItems.length === 0 ? (
                                    <div className="text-center text-gray-500 py-8">Queue is empty</div>
                                ) : (
                                    [...queueItems]
                                        .sort((a, b) => {
                                            return sortOrder === 'newest' ? b.queue_id - a.queue_id : a.queue_id - b.queue_id;
                                        })
                                        .map(item => (
                                            <div key={item.queue_id} className="p-3 border-l-4 flex justify-between items-start">
                                                <div>
                                                    <div className="flex gap-2 items-center mb-1">
                                                        <span className="font-semibold">Queue ID: {item.queue_id}</span>
                                                        <Badge variant={item.status as any}>{item.status.toUpperCase()}</Badge>
                                                    </div>
                                                    <div className="text-xs text-gray-500">
                                                        Command: <span className="font-semibold text-foreground">{item.command_name}</span> | Queued: {new Date(item.queued_at).toLocaleString()}
                                                    </div>
                                                    {item.parameters && Object.keys(item.parameters).length > 0 && (
                                                        <><span className="block mt-2">Body</span>
                                                            <div className="text-xs text-gray-400 mt-1 space-y-1 border-l-4 pl-2">
                                                                {Object.entries(item.parameters).map(([key, value]) => (
                                                                    <div key={key}>
                                                                        <span className="font-medium text-gray-500">{key}:</span> {formatParameterValue(value)}
                                                                    </div>
                                                                ))}
                                                            </div></>
                                                    )}
                                                </div>
                                                <div>
                                                    <Button
                                                        variant="destructive"
                                                        size="sm"
                                                        onClick={() => handleCancel(item.queue_id)}
                                                        disabled={item.status !== 'queued'}
                                                    >
                                                        Cancel
                                                    </Button>
                                                </div>
                                            </div>
                                        ))
                                )}
                            </div>
                        </CardContent>
                    </Card>
                )}
            </div>
        </div>
    );
}
