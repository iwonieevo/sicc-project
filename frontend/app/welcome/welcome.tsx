import { Link } from "react-router";
import { Button } from "~/components/ui/button";
import { useAuth } from "~/providers/AuthProvider";

export function Welcome() {
  const { user, loading } = useAuth()

  return (
    <main className="flex items-center justify-center pt-16 pb-4">
      {!loading && (
        <div className="flex-1 flex flex-col items-center gap-4 min-h-0">
          <header className="flex flex-col items-center gap-9">
            <div className="w-[500px] max-w-[100vw] p-4">
              <h1 className="text-center text-4xl font-bold">SICC Client</h1>
            </div>
          </header>
          {user ? (
            <>
              <p className="text-center text-lg">Welcome back!</p>
              <div className="max-w-[300px] w-full space-x-2 px-4 flex items-center justify-center">
                <Button variant="default" size="lg" asChild className="mb-0">
                  <Link to="/dashboard">Go to Dashboard</Link>
                </Button>
              </div></>
          ) : (
            <div className="max-w-[300px] w-full space-x-2 px-4 flex items-center justify-center">
              <Button variant="default" size="lg" asChild className="mb-0">
                <Link to="/signup">Create new account</Link>
              </Button>
              <Button variant="outline" size="lg" asChild>
                <Link to="/login">Sign in</Link>
              </Button>
            </div>
          )}
        </div>
      )}
    </main>
  );
}