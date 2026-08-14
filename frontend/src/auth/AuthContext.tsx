import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { authApi } from "@/api/endpoints";
import { tokenStore } from "@/api/client";
import type { User } from "@/types";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string, rememberMe?: boolean) => Promise<User>;
  logout: (allSessions?: boolean) => Promise<void>;
  refreshUser: () => Promise<void>;
  can: (permission: string) => boolean;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const loadUser = useCallback(async () => {
    if (!tokenStore.access) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      setUser(await authApi.me());
    } catch {
      tokenStore.clear();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadUser();
  }, [loadUser]);

  useEffect(() => {
    const onExpired = () => {
      tokenStore.clear();
      setUser(null);
    };
    window.addEventListener("asa:session-expired", onExpired);
    return () => window.removeEventListener("asa:session-expired", onExpired);
  }, []);

  const login = useCallback(async (email: string, password: string, rememberMe = false) => {
    const tokens = await authApi.login(email, password, rememberMe);
    tokenStore.save(tokens.access_token, tokens.refresh_token);
    setUser(tokens.user);
    return tokens.user;
  }, []);

  const logout = useCallback(async (allSessions = false) => {
    try {
      await authApi.logout(allSessions);
    } catch {
      // Logging out locally must succeed even if the API is unreachable.
    }
    tokenStore.clear();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      login,
      logout,
      refreshUser: loadUser,
      can: (permission: string) => Boolean(user?.permissions?.includes(permission)),
      isAdmin: user?.role === "hr_admin",
    }),
    [user, loading, login, logout, loadUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return context;
}
