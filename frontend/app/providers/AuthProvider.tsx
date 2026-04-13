import { createContext, useContext, useState, useEffect, useMemo } from "react";
import { Outlet, useNavigate } from "react-router";

interface AuthContextType {
    user: String | null;
    login: (data: string) => Promise<void>;
    logout: () => void;
}

const defaultValue: AuthContextType = {
    user: null, // TODO: for now, it's access token, but it will be user data when backend is ready
    login: async () => { },
    logout: () => { }
};

export const AuthContext = createContext(defaultValue);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState(defaultValue.user);

    useEffect(() => {
        fetch("/api/me", {
            credentials: "include",
        })
            .then((res) => res.json())
            .then((data) => {
                if (data.user) {
                    setUser(data.user);
                }
            })
            .catch((err) => {
                console.error("Failed to fetch user:", err);
            });
    }, []);

    const navigate = useNavigate();
    const value = useMemo(() => {
        // call this function when you want to authenticate the user
        const login = async (userData: string) => {
            setUser(userData);
            localStorage.setItem("accessToken", userData); // TODO: to remove when backend is ready (HttpOnly cookie will be used instead)
            navigate("/");
        };

        // call this function to sign out logged in user
        const logout = () => {
            setUser(null);
            localStorage.removeItem("accessToken"); // TODO: to remove when backend is ready (HttpOnly cookie will be used instead)
            navigate("/login", { replace: true });
        };

        return { user, login, logout };
    }, [user, navigate, setUser]);

    return (
        <AuthContext value={value}>
            {children}
        </AuthContext>
    );
}