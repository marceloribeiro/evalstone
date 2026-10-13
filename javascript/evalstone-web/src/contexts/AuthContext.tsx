"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, getToken, setToken } from "@/lib/api";
import type { AuthOut, User } from "@/lib/types";

type AuthState = {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, firstName: string, lastName: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTok] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const t = getToken();
    const finish = () => {
      if (!cancelled) setLoading(false);
    };
    if (!t) {
      Promise.resolve().then(finish);
      return () => {
        cancelled = true;
      };
    }
    api<User>("/me", { token: t })
      .then((u) => {
        if (!cancelled) {
          setTok(t);
          setUser(u);
        }
      })
      .catch(() => setToken(null))
      .finally(finish);
    return () => {
      cancelled = true;
    };
  }, []);

  const accept = useCallback((out: AuthOut) => {
    setToken(out.token);
    setTok(out.token);
    setUser(out.user);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      token,
      loading,
      login: async (email, password) =>
        accept(await api<AuthOut>("/auth/login", { method: "POST", body: { email, password }, token: null })),
      register: async (email, password, first_name, last_name) =>
        accept(
          await api<AuthOut>("/auth/register", {
            method: "POST",
            body: { email, password, first_name, last_name },
            token: null,
          }),
        ),
      logout: () => {
        setToken(null);
        setTok(null);
        setUser(null);
      },
    }),
    [user, token, loading, accept],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
