import { useEffect } from "react";
import { useNavigate, Outlet, Navigate } from "react-router";
import { useAuth } from "../../providers/AuthProvider";

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
    const data = useAuth();

    if (!!data?.user) {
        return <Navigate to="/" replace />;
    }
    return <Outlet />;
};