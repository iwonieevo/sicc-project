import { Link } from "react-router";
import { Button } from "~/components/ui/button";

export default function Page() {
    return (
        <main className="flex items-center justify-center pt-16 pb-4">
            <div className="flex-1 flex flex-col items-center gap-4 min-h-0">
                <header className="flex flex-col items-center gap-9">
                    <div className="w-[500px] max-w-[100vw] p-4">
                        <h1 className="text-center text-4xl font-bold">Dashboard</h1>
                    </div>
                </header>
                <div className="max-w-[300px] w-full space-x-2 px-4 flex items-center justify-center">
                    <Button variant="default" size="lg" asChild className="mb-0">
                        <Link to="/dashboard/simple-message">Send Simple Message (String Test)</Link>
                    </Button>
                    <Button variant="outline" size="lg" asChild className="mb-0">
                        <Link to="/dashboard/logs">View Logs (WIP)</Link>
                    </Button>
                </div>
            </div>
        </main>
    )
}
