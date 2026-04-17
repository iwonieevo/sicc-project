"use client"

import { useState } from "react"
import { useForm, Controller } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import * as z from "zod"

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
import { Link, useNavigate } from "react-router"
import { useAuth } from "~/providers/AuthProvider"
import { Textarea } from "../ui/textarea"
import { Select, SelectContent, SelectGroup, SelectItem, SelectValue, SelectTrigger } from "../ui/select"

// 1. Define the validation schema
const simpleMessageSchema = z.object({
    agentId: z.string().min(1, "Agent ID cannot be empty"),
    message: z.string().min(1, "Message cannot be empty"),
})

// read Vite env var (string) and convert to number; default to 2 if missing
const numAgents = Number(import.meta.env.VITE_NUM_AGENTS ?? 2);

// build an array like [{ value: "1", label: "Raspberry Pi 1" }, ...]
const agentOptions = Array.from({ length: Math.max(1, numAgents) }, (_, i) => ({
  value: String(i + 1),
  label: `Raspberry Pi ${i + 1}`,
}));

// 2. Extract the type from the schema
type SimpleMessageValues = z.infer<typeof simpleMessageSchema>

export function SimpleMessageForm({
    className,
    ...props
}: React.ComponentProps<"div">) {
    const [serverError, setServerError] = useState<string | null>(null)
    const navigate = useNavigate()
    const { login } = useAuth()

    // 3. Initialize the form
    const {
        control,
        register,
        handleSubmit,
        formState: { errors, isSubmitting },
    } = useForm<SimpleMessageValues>({
        resolver: zodResolver(simpleMessageSchema),
        defaultValues: {
            agentId: "",
            message: "",
        },
    })

    // 4. Handle form submission
    const onSubmit = async (data: SimpleMessageValues) => {
        setServerError(null)
        try {
            const response = await fetch("/api/simple-message", {
                method: "POST",
                credentials: "include",
                headers: { "Content-Type": "application/json", authorization: "Bearer " + localStorage.getItem("accessToken") }, // TODO: to remove when backend is ready (HttpOnly cookie will be used instead)
                body: JSON.stringify(data),
            })

            const result = await response.json()

            if (!response.ok) {
                throw new Error(result.detail || "Something went wrong")
            }

            console.log("Sent simple message successfully:", result)
        } catch (error: any) {
            setServerError(error.message)
        }
    }

    return (
        <div className={cn("flex flex-col gap-6", className)} {...props}>
            <Card>
                <CardHeader>
                    <CardTitle>Send Simple Message</CardTitle>
                    <CardDescription>
                        Enter the agent ID and message below to send a simple message
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <form onSubmit={handleSubmit(onSubmit)}>
                        <FieldGroup>
                            {/* Agent Field */}
                            <Field>
                                <FieldLabel htmlFor="agentId">Agent ID</FieldLabel>
                                <Controller
                                    name="agentId"
                                    control={control}
                                    render={({ field }) => (
                                        <Select onValueChange={field.onChange} value={field.value} disabled={isSubmitting}>
                                            <SelectTrigger className="w-[180px]" id="agentId">
                                                <SelectValue placeholder="Select Agent" />
                                            </SelectTrigger>
                                            <SelectContent>
                                            <SelectGroup>
                                                {agentOptions.map((ag) => (
                                                <SelectItem key={ag.value} value={ag.value}>
                                                    {ag.label}
                                                </SelectItem>
                                                ))}
                                            </SelectGroup>
                                            </SelectContent>
                                        </Select>)}
                                />
                                {errors.agentId && (
                                    <p className="text-sm font-medium text-destructive">{errors.agentId.message}</p>
                                )}
                            </Field>

                            {/* Message Field */}
                            <Field>
                                <div className="flex items-center">
                                    <FieldLabel htmlFor="message">Message</FieldLabel>
                                </div>
                                <Textarea
                                    {...register("message")}
                                    id="message"
                                    disabled={isSubmitting}
                                    rows={5}
                                />
                                {errors.message && (
                                    <p className="text-sm font-medium text-destructive">{errors.message.message}</p>
                                )}
                            </Field>

                            {/* Server-side Error Display */}
                            {serverError && (
                                <p className="text-sm text-center font-medium text-destructive">
                                    {serverError}
                                </p>
                            )}

                            <Field>
                                <Button type="submit" className="w-full" disabled={isSubmitting}>
                                    {isSubmitting ? "Sending..." : "Send"}
                                </Button>
                            </Field>
                        </FieldGroup>
                    </form>
                </CardContent>
            </Card>
        </div>
    )
}