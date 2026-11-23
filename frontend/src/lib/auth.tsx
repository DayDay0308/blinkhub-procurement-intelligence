import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, auth } from "./api";
import type { Role, User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
  can: (...roles: Role[]) => boolean;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(Boolean(auth.token));
  const qc = useQueryClient();

  const signOut = useCallback(() => {
    auth.set(null);
    setUser(null);
    qc.clear();
  }, [qc]);

  useEffect(() => {
    auth.onUnauthorized(signOut);
    if (!auth.token) return;
    api<User>("/auth/me")
      .then(setUser)
      .catch(signOut)
      .finally(() => setLoading(false));
  }, [signOut]);

  const signIn = async (email: string, password: string) => {
    const t = await api<{ access_token: string }>("/auth/login", { form: { username: email, password } });
    auth.set(t.access_token);
    setUser(await api<User>("/auth/me"));
  };

  const can = (...roles: Role[]) => Boolean(user && roles.includes(user.role));

  return <Ctx.Provider value={{ user, loading, signIn, signOut, can }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
