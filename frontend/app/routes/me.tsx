import type { Route } from "../+types/root";

export async function clientLoader({ params }: Route.ClientLoaderArgs) {
    const data: { user: String } = await fetch("/api/me", {
        credentials: "include",
        headers: {
            authorization: "Bearer " + localStorage.getItem("accessToken"), // TODO: for now, it's access token, but it will be removed when backend is ready
        },
    }).then((res) => res.json());

    return data;
}

export function HydrateFallback() {
    return <div>Loading...</div>;
}

export default function Page({ loaderData }: Route.ComponentProps) {
    return (
        <div className="flex items-center justify-center pt-16 pb-4">
            <div>
                /api/me: {JSON.stringify(loaderData as any)}
            </div>
        </div>
    )
}
