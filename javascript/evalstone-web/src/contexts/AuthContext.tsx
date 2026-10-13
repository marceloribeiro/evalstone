"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, getToken, isUnauthorized, setToken, UNAUTHORIZED_EVENT } from "@/lib/api";
import type { AuthOut, User } from "@/lib/types";

type AuthState = {
  user: User | null;
  token: string | null;
  loading: boolean;
  /** `/me` failed for a reason other than 401 (API down, 502): the token is kept; `retry()` asks again. */
  unreachable: boolean;
  retry: () => void;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, firstName: string, lastName: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTok] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [unreachable, setUnreachable] = useState(false);
  const [attempt, setAttempt] = useState(0);

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
          setUnreachable(false);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        if (isUnauthorized(err)) setToken(null); // the session is over: only then forget the token
        else setUnreachable(true); // a blip (deploy, 502): keep the 7-day token, offer a retry
      })
      .finally(finish);
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  // A request made with the stored token came back 401 mid-session: sign out everywhere.
  useEffect(() => {
    const onUnauthorized = () => {
      setTok(null);
      setUser(null);
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const accept = useCallback((out: AuthOut) => {
    setToken(out.token);
    setTok(out.token);
    setUser(out.user);
    setUnreachable(false);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      token,
      loading,
      unreachable,
      retry: () => {
        setLoading(true);
        setAttempt((a) => a + 1);
      },
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
    [user, token, loading, unreachable, accept],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
