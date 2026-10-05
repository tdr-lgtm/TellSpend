/**
* Who is signed in, and how to sign out.
*/
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { getMe } from "../lib/api";
import { clearToken } from "../lib/token";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: getMe,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  return () => {
    clearToken();
    queryClient.clear();
    navigate("/login", { replace: true });
  };
}