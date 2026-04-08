import { useEffect } from "react";
import { useNavigate, Outlet, Navigate } from "react-router";
import { useAuth } from "../../providers/AuthProvider";

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
    const navigate = useNavigate();
    const data = useAuth();

    useEffect(() => {
        console.log("ProtectedRoute: checking authentication", data);
        if (!data?.user) {
            // user is not authenticated
            navigate("/login");
            return;
        }
    }, [data, navigate]);

    return <Outlet />;
};