import { Navigate, Outlet } from "react-router";
import { DashboardSidebar } from "./sidebar";

export default function DashboardLayout() {
    return <div className="flex h-full p-4">
        <DashboardSidebar />
        <div className="flex-1">
            <Outlet />
        </div>
    </div>;
}