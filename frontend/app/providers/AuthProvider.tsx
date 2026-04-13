import { createContext, useContext, useState, useEffect, useMemo } from "react";
import { Outlet, useNavigate } from "react-router";

interface AuthContextType {
    loading: boolean;
    user: String | null;
    login: (data: string) => Promise<void>;
    logout: () => void;
}

const defaultValue: AuthContextType = {
    loading: true,
    user: null, // TODO: for now, it's access token, but it will be user data when backend is ready
    login: async () => { },
    logout: () => { }
};

export const AuthContext = createContext(defaultValue);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [user, setUser] = useState(defaultValue.user);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch("/api/me", {
            credentials: "include",
            headers: {
                authorization: "Bearer " + localStorage.getItem("accessToken"), // TODO: for now, it's access token, but it will be removed when backend is ready
            },
        })
            .then((res) => res.json())
            .then((data) => {
                setUser(localStorage.getItem("accessToken"));
                setLoading(false);
            })
            .catch((err) => {
                localStorage.removeItem("accessToken")
                console.error("Failed to fetch user:", err);
                setLoading(false);
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

        return { user, login, logout, loading };
    }, [user, navigate, setUser, loading]);

    return (
        <AuthContext value={value}>
            {children}
        </AuthContext>
    );
}