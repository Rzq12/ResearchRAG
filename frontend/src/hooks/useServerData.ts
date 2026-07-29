import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/context/AuthContext";
import { getConfig, getKbStats, listDocuments } from "@/lib/api";

/**
 * The user id is still part of every query KEY so switching accounts cannot
 * surface the previous account's cached rows — but it is no longer passed to
 * the API, which derives identity from the bearer token instead.
 */
function useScopeKey(): string {
  const { session } = useAuth();
  return session?.userId ?? "anonymous";
}

/** App config + model catalog (public, fetched once). */
export function useConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: getConfig,
    staleTime: Infinity,
  });
}

/** Documents in the authenticated user's knowledge base. */
export function useDocuments() {
  const scope = useScopeKey();
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ["documents", scope],
    queryFn: listDocuments,
    enabled: isAuthenticated,
  });
}

/** Knowledge-base stats (chunk + document counts). */
export function useKbStats() {
  const scope = useScopeKey();
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ["kb-stats", scope],
    queryFn: getKbStats,
    enabled: isAuthenticated,
  });
}
