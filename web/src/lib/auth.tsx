"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api, tokenStore } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  organization: string;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
  /** Owners and admins may change configuration; supervisors are read-only. */
  canConfigure: boolean;
}

const AuthContext = createContext<AuthState | null>(null);
const ORG_KEY = "ca.organization";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [organization, setOrganization] = useState("");
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    // Restore the session on load: a stored token may still be valid, and a
    // stale one is discarded rather than left to fail on the first request.
    if (!tokenStore.access) {
      setLoading(false);
      return;
    }
    setOrganization(window.localStorage.getItem(ORG_KEY) ?? "");
    api
      .me()
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false));
  }, []);

  const signIn = useCallback(
    async (email: string, password: string) => {
      const session = await api.login(email, password);
      tokenStore.set(session.tokens.access_token, session.tokens.refresh_token);
      window.localStorage.setItem(ORG_KEY, session.organization_name);
      setUser(session.user);
      setOrganization(session.organization_name);
      router.push("/");
    },
    [router],
  );

  const signOut = useCallback(() => {
    tokenStore.clear();
    window.localStorage.removeItem(ORG_KEY);
    setUser(null);
    router.push("/login");
  }, [router]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      organization,
      loading,
      signIn,
      signOut,
      canConfigure: user?.role === "owner" || user?.role === "admin",
    }),
    [user, organization, loading, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
