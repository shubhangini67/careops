"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiGetMe, apiLogin, apiRegister, LoginRequest, RegisterRequest, UserMe } from "@/lib/api";
import { clearAuthCookie, getAuthToken, setAuthCookie } from "@/lib/auth-cookies";

interface AuthState {
  user: UserMe | null;
  loading: boolean;
  login: (body: LoginRequest) => Promise<void>;
  register: (body: RegisterRequest) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserMe | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const fetchMe = useCallback(async () => {
    const token = getAuthToken();
    if (!token) { setLoading(false); return; }
    try {
      const me = await apiGetMe();
      setUser(me);
    } catch {
      clearAuthCookie();
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchMe(); }, [fetchMe]);

  const login = useCallback(async (body: LoginRequest) => {
    const { access_token } = await apiLogin(body);
    setAuthCookie(access_token);
    const me = await apiGetMe();
    setUser(me);
    router.push("/dashboard");
  }, [router]);

  const register = useCallback(async (body: RegisterRequest) => {
    const { access_token } = await apiRegister(body);
    setAuthCookie(access_token);
    const me = await apiGetMe();
    setUser(me);
    router.push("/dashboard");
  }, [router]);

  const logout = useCallback(() => {
    clearAuthCookie();
    setUser(null);
    router.push("/login");
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
