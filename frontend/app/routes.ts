import { type RouteConfig, index, route, layout } from "@react-router/dev/routes";

export default [
    index("routes/home.tsx"),
    layout("./components/auth/public-only-route.tsx", [
        route("login", "routes/login.tsx"),
        route("signup", "routes/signup.tsx"),
    ]),
    layout("./components/auth/protected-route.tsx", [
        route("me", "routes/me.tsx"),
    ]),
] satisfies RouteConfig;
