import { createFileRoute, Outlet, useNavigate, Link, useRouterState } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { tokenStore, StatsAPI, type UserStats } from "../lib/api";
import { useAuth } from "../lib/use-auth";
import { Logo } from "../components/Logo";
import { LogOut, Flame, Trophy } from "lucide-react";

export const Route = createFileRoute("/_authenticated")({
  component: AuthLayout,
});

function AuthLayout() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const path = useRouterState({ select: (s) => s.location.pathname });

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!tokenStore.getAccess()) navigate({ to: "/login", replace: true });
  }, [navigate, path]);

  // Real stats from backend (refetched on navigation so they update after activity)
  const [stats, setStats] = useState<UserStats | null>(null);
  useEffect(() => {
    if (typeof window === "undefined" || !tokenStore.getAccess()) return;
    StatsAPI.get().then(setStats).catch(() => {});
  }, [path]);

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 glass border-b border-black/[0.07]">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-6">
            <Logo />
            <nav className="hidden md:flex items-center gap-1 text-sm">
              <Link to="/dashboard" className="rounded-lg px-3 py-1.5 text-muted-foreground transition hover:bg-black/[0.04] hover:text-foreground [&.active]:bg-black/[0.07] [&.active]:text-foreground"
                    activeProps={{ className: "active" }}>Courses</Link>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-1.5 rounded-full glass px-3 py-1.5 text-xs">
              <Flame className="h-3.5 w-3.5 text-orange-500" />
              <span className="font-semibold">{stats?.streak ?? 0} days active</span>
            </div>
            <div className="hidden sm:flex items-center gap-1.5 rounded-full glass px-3 py-1.5 text-xs">
              <Trophy className="h-3.5 w-3.5 text-amber-500" />
              <span className="font-semibold">Lvl {stats?.level ?? 1}</span>
            </div>
            <div className="text-sm text-muted-foreground hidden sm:block">{user?.name || user?.email}</div>
            <button onClick={logout} className="rounded-lg p-2 text-muted-foreground hover:bg-black/[0.04] hover:text-foreground transition" title="Sign out">
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
