import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";

interface AuthState {
  loading: boolean;
  ownerExists: boolean;
  username: string | null;
  bootstrap: (username: string, password: string) => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [ownerExists, setOwnerExists] = useState(false);
  const [username, setUsername] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const status = await api.get<{ owner_exists: boolean }>("/api/auth/status");
      setOwnerExists(status.owner_exists);
      if (status.owner_exists) {
        try {
          const me = await api.get<{ username: string }>("/api/auth/me");
          setUsername(me.username);
        } catch {
          setUsername(null);
        }
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const bootstrap = useCallback(async (u: string, p: string) => {
    const res = await api.post<{ username: string }>("/api/auth/bootstrap", { username: u, password: p });
    setOwnerExists(true);
    setUsername(res.username);
  }, []);

  const login = useCallback(async (u: string, p: string) => {
    const res = await api.post<{ username: string }>("/api/auth/login", { username: u, password: p });
    setUsername(res.username);
  }, []);

  const logout = useCallback(async () => {
    await api.post("/api/auth/logout");
    setUsername(null);
  }, []);

  return <AuthContext.Provider value={{ loading, ownerExists, username, bootstrap, login, logout }}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components -- deliberate: Provider + hook stay together
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
