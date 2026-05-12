import { type RouteConfig, index, route, layout, prefix } from "@react-router/dev/routes";

export default [
    index("routes/home.tsx"),
    layout("./components/auth/public-only-route.tsx", [
        route("login", "routes/login.tsx"),
        route("signup", "routes/signup.tsx"),
    ]),
    layout("./components/auth/protected-route.tsx", [
        route("me", "routes/me.tsx"),
        layout("./components/dashboard/_layout.tsx", [
            ...prefix("dashboard", [
                index("routes/dashboard/home.tsx"),
                route("commands", "routes/dashboard/commands.tsx"),
                route("logs", "routes/dashboard/logs.tsx"),
                route("queue", "routes/dashboard/queue.tsx"),
            ]),
        ]),
    ]),
] satisfies RouteConfig;