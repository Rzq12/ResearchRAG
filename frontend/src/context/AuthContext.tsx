import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";

import { useLocalStorage } from "@/hooks/useLocalStorage";

interface Session {
  userId: string;
  displayName: string;
}

interface AuthContextValue {
  session: Session | null;
  isAuthenticated: boolean;
  login: (userId: string, displayName: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useLocalStorage<Session | null>("rr_session", null);

  const login = useCallback(
    (userId: string, displayName: string) => setSession({ userId, displayName }),
    [setSession],
  );

  const logout = useCallback(() => setSession(null), [setSession]);

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      isAuthenticated: Boolean(session?.userId),
      login,
      logout,
    }),
    [session, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
