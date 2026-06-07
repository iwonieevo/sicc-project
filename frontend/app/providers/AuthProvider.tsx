import { createContext, useContext, useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router";
import { clearSecureTransportSession, secureFetch } from "~/lib/secure/secure-fetch";

interface AuthContextType {
  loading: boolean;
  user: { email: string } | null;
  login: (email: string, token: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  loading: true,
  user: null,
  login: () => {},
  logout: () => {},
});

export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<{ email: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const token = localStorage.getItem("accessToken");
    if (!token) {
      setLoading(false);
      return;
    }

    secureFetch("/api/me", {
      credentials: "include",
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => (res.ok ? res.json<{ email: string }>() : Promise.reject()))
      .then((data) => setUser({ email: data.email }))
      .catch(() => localStorage.removeItem("accessToken"))
      .finally(() => setLoading(false));
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      login: (email: string, token: string) => {
        localStorage.setItem("accessToken", token);
        setUser({ email });
        navigate("/dashboard");
      },
      logout: () => {
        localStorage.removeItem("accessToken");
        clearSecureTransportSession();
        setUser(null);
        navigate("/login", { replace: true });
      },
    }),
    [user, loading, navigate],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
