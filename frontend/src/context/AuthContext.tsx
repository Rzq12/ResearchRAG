import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { login as apiLogin, logout as apiLogout } from "@/lib/api";
import { getSession, subscribe, type Session } from "@/lib/authStore";

interface AuthContextValue {
  session: Session | null;
  isAuthenticated: boolean;
  /** Verifies credentials with the server and stores the token pair. */
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  // The token store is the source of truth. React mirrors it so that a session
  // cleared deep inside the API client (expired refresh token) instantly flips
  // the UI back to the login screen, with no prop drilling.
  const [session, setLocalSession] = useState<Session | null>(getSession);

  useEffect(() => subscribe(setLocalSession), []);

  const login = useCallback(async (username: string, password: string) => {
    await apiLogin(username, password); // throws ApiError on bad credentials
  }, []);

  const logout = useCallback(async () => {
    await apiLogout(); // revokes the refresh-token family server-side
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      isAuthenticated: Boolean(session?.accessToken),
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
