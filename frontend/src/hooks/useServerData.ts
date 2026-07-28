import { useQuery } from "@tanstack/react-query";

import { getConfig, getKbStats, listDocuments } from "@/lib/api";

/** App config + model catalog (fetched once). */
export function useConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: getConfig,
    staleTime: Infinity,
  });
}

/** Documents in the user's knowledge base. */
export function useDocuments(userId: string | null) {
  return useQuery({
    queryKey: ["documents", userId],
    queryFn: () => listDocuments(userId),
    enabled: userId !== undefined,
  });
}

/** Knowledge-base stats (chunk + document counts). */
export function useKbStats(userId: string | null) {
  return useQuery({
    queryKey: ["kb-stats", userId],
    queryFn: () => getKbStats(userId),
    enabled: userId !== undefined,
  });
}
