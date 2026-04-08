import type { Route } from "../+types/root";

export async function clientLoader({ params }: Route.ClientLoaderArgs) {
    const data: { user: String } = await fetch("/api/me", {
        credentials: "include",
    }).then((res) => res.json());

    return data;
}

export function HydrateFallback() {
    return <div>Loading...</div>;
}

export default function Page({ loaderData }: Route.ComponentProps) {
    const { me: { email } } = loaderData as any
    return (
        <div className="flex items-center justify-center pt-16 pb-4">
            <div>
                Your email is: {email}
            </div>
        </div>
    )
}
