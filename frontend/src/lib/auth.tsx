// This file exports ONLY the AuthProvider component.
// useAuth hook is in ./use-auth.ts — kept separate for Vite Fast Refresh compatibility
// (Fast Refresh breaks when a file mixes component exports with non-component exports).
import { createContext, useEffect, useState, type ReactNode } from "react";
import { AuthAPI, tokenStore } from "./api";

export type User = { email: string; name?: string } | null;
export type AuthCtx = {
  user: User;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, name: string, password: string) => Promise<void>;
  logout: () => void;
};

export const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const t = tokenStore.getAccess();
    if (t) {
      const stored = localStorage.getItem("eduprep_user");
      if (stored) setUser(JSON.parse(stored));
    }
    setLoading(false);
  }, []);

  const applyAuth = (data: any) => {
    const access = data.access_token ?? data.accessToken;
    const refresh = data.refresh_token ?? data.refreshToken;
    if (access) tokenStore.set(access, refresh);
    const u = data.user ?? { email: data.email, name: data.name };
    if (u) {
      localStorage.setItem("eduprep_user", JSON.stringify(u));
      setUser(u);
    }
  };

  const login: AuthCtx["login"] = async (email, password) => {
    const data = await AuthAPI.login({ email, password });
    applyAuth({ ...data, email });
  };

  const register: AuthCtx["register"] = async (email, name, password) => {
    const data = await AuthAPI.register({ email, name, password });
    applyAuth({ ...data, email, name });
  };

  const logout = () => {
    tokenStore.clear();
    localStorage.removeItem("eduprep_user");
    setUser(null);
    window.location.href = "/login";
  };

  return <Ctx.Provider value={{ user, loading, login, register, logout }}>{children}</Ctx.Provider>;
}
