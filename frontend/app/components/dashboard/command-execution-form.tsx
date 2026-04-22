"use client"

import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { cn } from "~/lib/utils"
import { Button } from "~/components/ui/button"
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "~/components/ui/card"
import {
    Field,
    FieldDescription,
    FieldGroup,
    FieldLabel,
} from "~/components/ui/field"
import { Input } from "~/components/ui/input"
import { Select, SelectContent, SelectGroup, SelectItem, SelectValue, SelectTrigger } from "~/components/ui/select"

interface Device {
    id: number
    name: string
    status: string
    last_seen?: string
}

interface CommandParameter {
    id: number
    name: string
    param_type: string
    is_required: boolean
    default_value?: string
    description?: string
}

interface Command {
    id: number
    name: string
    description?: string
    parameters: CommandParameter[]
}

interface ExecutionStatus {
    queue_id: number
    device_id: number
    command_id: number
    status: 'queued' | 'running' | 'done' | 'error'
    result?: string
    is_error?: boolean
    queued_at?: string
    started_at?: string
    finished_at?: string
}

export function CommandExecutionForm({
    className,
    ...props
}: React.ComponentProps<"div">) {
    const [devices, setDevices] = useState<Device[]>([])
    const [commands, setCommands] = useState<Command[]>([])
    const [selectedDevice, setSelectedDevice] = useState<string>("")
    const [selectedCommand, setSelectedCommand] = useState<string>("")
    const [currentCommand, setCurrentCommand] = useState<Command | null>(null)
    const [serverError, setServerError] = useState<string | null>(null)
    const [isLoading, setIsLoading] = useState(false)
    const [executionStatus, setExecutionStatus] = useState<ExecutionStatus | null>(null)
    const [isPolling, setIsPolling] = useState(false)

    const { register, handleSubmit, formState: { isSubmitting }, reset } = useForm({
        defaultValues: {}
    })

    useEffect(() => {
        const fetchData = async () => {
            try {
                const token = localStorage.getItem("accessToken");
                const [devicesRes, commandsRes] = await Promise.all([
                    fetch('/api/devices', {
                        credentials: "include",
                        headers: { "Authorization": `Bearer ${token}` }
                    }),
                    fetch('/api/commands', {
                        credentials: "include",
                        headers: { "Authorization": `Bearer ${token}` }
                    })
                ]);

                if (devicesRes.ok) {
                    const devicesData = await devicesRes.json();
                    setDevices(devicesData || []);
                }

                if (commandsRes.ok) {
                    const commandsData = await commandsRes.json();
                    setCommands(commandsData || []);
                }
            } catch (error) {
                console.error("Failed to fetch devices/commands:", error);
            }
        };

        fetchData();
    }, []);

    useEffect(() => {
        if (selectedCommand) {
            const cmd = commands.find(c => c.id.toString() === selectedCommand)
            setCurrentCommand(cmd || null)
            reset({})
        } else {
            setCurrentCommand(null)
        }
    }, [selectedCommand, commands, reset])

    useEffect(() => {
        if (!executionStatus || !isPolling) return
        
        if (executionStatus.status === 'done' || executionStatus.status === 'error') {
            setIsPolling(false)
            return
        }

        const interval = setInterval(async () => {
            try {
                const token = localStorage.getItem("accessToken");
                const res = await fetch(`/api/status/${executionStatus.queue_id}`, {
                    credentials: "include",
                    headers: { "Authorization": `Bearer ${token}` }
                });

                if (res.ok) {
                    const data = await res.json();
                    setExecutionStatus(data);
                    
                    if (data.status === 'done' || data.status === 'error') {
                        setIsPolling(false);
                    }
                }
            } catch (error) {
                console.error("Failed to poll execution status:", error);
            }
        }, 2000);

        return () => clearInterval(interval)
    }, [executionStatus, isPolling])

    const onSubmit = async (formData: any) => {
        if (!selectedDevice || !selectedCommand) {
            setServerError("Please select both device and command");
            return;
        }

        const selectedDeviceObj = devices.find(d => d.id.toString() === selectedDevice);
        if (selectedDeviceObj?.status === 'offline') {
            setServerError("Cannot execute command on offline device");
            return;
        }

        setServerError(null);
        setIsLoading(true);
        setExecutionStatus(null);

        try {
            const parameters: Record<string, any> = {};
            
            if (currentCommand && currentCommand.parameters.length > 0) {
                for (const param of currentCommand.parameters) {
                    const value = formData[`param_${param.id}`];
                    if (param.is_required && (value === undefined || value === "")) {
                        setServerError(`Missing required parameter: ${param.name}`);
                        setIsLoading(false);
                        return;
                    }
                    if (value !== undefined && value !== "") {
                        // Convert to proper type based on param_type
                        if (param.param_type === 'integer') {
                            const intValue = parseInt(value, 10);
                            if (isNaN(intValue)) {
                                setServerError(`Parameter '${param.name}' must be a valid integer`);
                                setIsLoading(false);
                                return;
                            }
                            parameters[param.name] = intValue;
                        } else {
                            parameters[param.name] = value;
                        }
                    }
                }
            }

            const response = await fetch("/api/execute", {
                method: "POST",
                credentials: "include",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${localStorage.getItem("accessToken")}`
                },
                body: JSON.stringify({
                    device_id: parseInt(selectedDevice),
                    command_id: parseInt(selectedCommand),
                    parameters: parameters
                }),
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.detail || "Failed to execute command");
            }

            setExecutionStatus({
                queue_id: result.queue_id,
                device_id: parseInt(selectedDevice),
                command_id: parseInt(selectedCommand),
                status: 'queued'
            });
            setIsPolling(true);
            reset({});

        } catch (error: any) {
            setServerError(error.message);
        } finally {
            setIsLoading(false);
        }
    };

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'online': return 'text-green-600'
            case 'busy': return 'text-yellow-600'
            case 'offline': return 'text-gray-400'
            default: return 'text-gray-600'
        }
    }

    const getExecutionStatusColor = (status: string) => {
        switch (status) {
            case 'queued': return 'text-yellow-600'
            case 'running': return 'text-blue-600'
            case 'done': return 'text-green-600'
            case 'error': return 'text-red-600'
            default: return 'text-gray-600'
        }
    }

    return (
        <div className={cn("w-full", className)} {...props}>
            <Card>
                <CardHeader>
                    <CardTitle>Execute Command</CardTitle>
                    <CardDescription>Select a device and command to execute</CardDescription>
                </CardHeader>
                <CardContent>
                    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
                        <FieldGroup>
                            <FieldLabel>Device</FieldLabel>
                            <Select value={selectedDevice} onValueChange={setSelectedDevice}>
                                <SelectTrigger>
                                    <SelectValue placeholder="Select a device" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectGroup>
                                        {devices.map(device => (
                                            <SelectItem key={device.id} value={device.id.toString()}>
                                                <span className="flex items-center gap-2">
                                                    {device.name}
                                                    <span className={getStatusColor(device.status)}>
                                                        ({device.status})
                                                    </span>
                                                </span>
                                            </SelectItem>
                                        ))}
                                    </SelectGroup>
                                </SelectContent>
                            </Select>
                            {devices.length === 0 && (
                                <FieldDescription>No devices available</FieldDescription>
                            )}
                        </FieldGroup>

                        <FieldGroup>
                            <FieldLabel>Command</FieldLabel>
                            <Select value={selectedCommand} onValueChange={setSelectedCommand}>
                                <SelectTrigger>
                                    <SelectValue placeholder="Select a command" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectGroup>
                                        {commands.map(cmd => (
                                            <SelectItem key={cmd.id} value={cmd.id.toString()}>
                                                {cmd.name}
                                            </SelectItem>
                                        ))}
                                    </SelectGroup>
                                </SelectContent>
                            </Select>
                            {currentCommand?.description && (
                                <FieldDescription>{currentCommand.description}</FieldDescription>
                            )}
                        </FieldGroup>

                        {currentCommand && currentCommand.parameters.length > 0 && (
                            <div className="space-y-4 border-t pt-4">
                                <h3 className="font-semibold text-sm">Parameters</h3>
                                {currentCommand.parameters.map(param => (
                                    <FieldGroup key={param.id}>
                                        <FieldLabel>
                                            {param.name}
                                            {param.is_required && <span className="text-red-500 ml-1">*</span>}
                                        </FieldLabel>
                                        {param.param_type === 'integer' ? (
                                            <Input
                                                type="number"
                                                {...register(`param_${param.id}`, {
                                                    required: param.is_required,
                                                })}
                                                placeholder={param.default_value || `Enter ${param.name}`}
                                            />
                                        ) : (
                                            <Input
                                                type="text"
                                                {...register(`param_${param.id}`, {
                                                    required: param.is_required,
                                                })}
                                                placeholder={param.default_value || `Enter ${param.name}`}
                                            />
                                        )}
                                        {param.description && (
                                            <FieldDescription>{param.description}</FieldDescription>
                                        )}
                                    </FieldGroup>
                                ))}
                            </div>
                        )}

                        {serverError && (
                            <div className="p-3 bg-red-100 text-red-800 rounded-md text-sm">
                                {serverError}
                            </div>
                        )}

                        {executionStatus && (
                            <div className="p-4 bg-gray-50 rounded-md border">
                                <h4 className="font-semibold mb-2">Execution Status</h4>
                                <p className="text-sm mb-2">
                                    <strong>Queue ID:</strong> {executionStatus.queue_id}
                                </p>
                                <p className="text-sm mb-2">
                                    <strong>Status:</strong>{' '}
                                    <span className={getExecutionStatusColor(executionStatus.status)}>
                                        {executionStatus.status}
                                    </span>
                                </p>
                                {executionStatus.queued_at && (
                                    <p className="text-xs text-gray-500">
                                        Queued: {new Date(executionStatus.queued_at).toLocaleString()}
                                    </p>
                                )}
                                {executionStatus.started_at && (
                                    <p className="text-xs text-gray-500">
                                        Started: {new Date(executionStatus.started_at).toLocaleString()}
                                    </p>
                                )}
                                {executionStatus.finished_at && (
                                    <p className="text-xs text-gray-500">
                                        Finished: {new Date(executionStatus.finished_at).toLocaleString()}
                                    </p>
                                )}
                                {executionStatus.result && (
                                    <div className="mt-2">
                                        <strong className="text-sm">Result:</strong>
                                        <pre className="bg-white p-2 rounded mt-1 text-xs overflow-auto max-h-48">
                                            {executionStatus.result}
                                        </pre>
                                    </div>
                                )}
                                {isPolling && (
                                    <p className="text-xs text-gray-600 mt-2">Polling for updates...</p>
                                )}
                            </div>
                        )}

                        <Button 
                            type="submit" 
                            className="w-full" 
                            disabled={isSubmitting || isLoading || !selectedDevice || !selectedCommand}
                        >
                            {isSubmitting || isLoading ? "Executing..." : "Execute Command"}
                        </Button>
                    </form>
                </CardContent>
            </Card>
        </div>
    )
}