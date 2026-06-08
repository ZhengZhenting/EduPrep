import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { tokenStore } from "../lib/api";

export const Route = createFileRoute("/")({
  component: Index,
});

function Index() {
  const navigate = useNavigate();
  useEffect(() => {
    const t = typeof window !== "undefined" ? tokenStore.getAccess() : null;
    navigate({ to: t ? "/dashboard" : "/login", replace: true });
  }, [navigate]);
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="h-10 w-10 animate-spin rounded-full border-2 border-transparent" style={{ borderTopColor: "oklch(0.7 0.2 290)" }} />
    </div>
  );
}
