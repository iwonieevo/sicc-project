import { useEffect } from "react";
import { useNavigate, Outlet, Navigate } from "react-router";
import { useAuth } from "../../providers/AuthProvider";

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
    const { user, loading } = useAuth();

    if (loading) {
        return <div>Loading...</div>;
    }

    if (user) {
        return <Navigate to="/" replace />;
    }
    return <Outlet />;
};