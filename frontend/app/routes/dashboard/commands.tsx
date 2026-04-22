import { CommandExecutionForm } from "~/components/dashboard/command-execution-form";
import { Navigate } from "react-router";
import { useAuth } from "~/providers/AuthProvider";

export default function Page() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex items-center justify-center pt-16">
        <p>Loading...</p>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="h-full flex w-full items-center justify-center p-6 md:p-10">
      <div className="w-full max-w-2xl">
        <CommandExecutionForm />
      </div>
    </div>
  );
}