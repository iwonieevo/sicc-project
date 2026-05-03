import { Link } from "react-router";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";

export default function Page() {
    return (
        <main className="flex items-center justify-center pt-16 pb-4">
            <div className="flex-1 flex flex-col items-center gap-4 min-h-0">
                <header className="flex flex-col items-center gap-9">
                    <div className="w-[500px] max-w-[100vw] p-4">
                        <h1 className="text-center text-4xl font-bold">Dashboard</h1>
                    </div>
                </header>
                <div className="max-w-[600px] w-full px-4">
                    <Card>
                        <CardHeader>
                            <CardTitle>IoT Command Center</CardTitle>
                            <CardDescription>
                                Execute commands on connected IoT devices
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-3">
                            <Button variant="default" size="lg" asChild className="w-full">
                                <Link to="/dashboard/commands">
                                    Execute Command
                                </Link>
                            </Button>
                            <Button variant="outline" size="lg" asChild className="w-full">
                                <Link to="/dashboard/logs">
                                    View Execution Logs
                                </Link>
                            </Button>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </main>
    )
}