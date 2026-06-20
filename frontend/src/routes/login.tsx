import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { motion } from "framer-motion";
import { useAuth } from "../lib/use-auth";
import { Logo } from "../components/Logo";
import { toast } from "sonner";
import { Loader2, Mail, Lock } from "lucide-react";

export const Route = createFileRoute("/login")({ component: LoginPage });

function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email, password);
      toast.success("Welcome back");
      navigate({ to: "/dashboard" });
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-md"
      >
        <div className="mb-8 flex justify-center"><Logo size="lg" /></div>

        <div className="glass-strong relative overflow-hidden rounded-2xl p-8 glow-brand">
          <div className="absolute -top-20 -right-20 h-40 w-40 rounded-full opacity-60 blur-3xl"
               style={{ background: "var(--gradient-brand)" }} />
          <h1 className="text-2xl font-bold mb-1">Welcome back</h1>
          <p className="text-sm text-muted-foreground mb-6">Sign in to continue learning</p>

          <form onSubmit={onSubmit} className="space-y-4">
            <Field icon={<Mail className="h-4 w-4" />} label="Email">
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                     className="w-full bg-transparent outline-none placeholder:text-muted-foreground"
                     placeholder="you@uni.de" />
            </Field>
            <Field icon={<Lock className="h-4 w-4" />} label="Password">
              <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
                     className="w-full bg-transparent outline-none placeholder:text-muted-foreground"
                     placeholder="••••••••" />
            </Field>

            <motion.button
              whileTap={{ scale: 0.97 }}
              whileHover={{ scale: 1.02 }}
              disabled={loading}
              className="relative w-full overflow-hidden rounded-xl py-3 font-semibold text-white glow-brand disabled:opacity-60"
              style={{ background: "var(--gradient-brand)" }}
            >
              {loading ? <Loader2 className="mx-auto h-5 w-5 animate-spin" /> : "Sign in"}
            </motion.button>
          </form>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            New here?{" "}
            <Link to="/register" className="font-semibold text-foreground hover:underline">Create an account</Link>
          </p>
        </div>
      </motion.div>
    </div>
  );
}

export function Field({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div className="group rounded-xl border border-black/[0.08] bg-black/[0.02] px-4 py-3 transition focus-within:border-primary/60 focus-within:shadow-[0_0_0_4px_oklch(0.56_0.24_15/0.12)]">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">{icon}<span>{label}</span></div>
      <div className="mt-1">{children}</div>
    </div>
  );
}
