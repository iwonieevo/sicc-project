import { SimpleMessageForm } from "~/components/dashboard/simple-message-form";

export default function Page() {
    return (
        <div className="h-full flex w-full items-center justify-center p-6 md:p-10">
            <div className="w-full max-w-sm">
                <SimpleMessageForm />
            </div>
        </div>
    )
}
