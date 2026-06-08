import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { motion } from "framer-motion";
import { useAuth } from "../lib/use-auth";
import { Logo } from "../components/Logo";
import { Field } from "./login";
import { toast } from "sonner";
import { Loader2, Mail, Lock, User } from "lucide-react";

export const Route = createFileRoute("/register")({ component: RegisterPage });

function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await register(email, name, password);
      toast.success("Account created");
      navigate({ to: "/dashboard" });
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
                  className="w-full max-w-md">
        <div className="mb-8 flex justify-center"><Logo size="lg" /></div>
        <div className="glass-strong relative overflow-hidden rounded-2xl p-8 glow-brand">
          <div className="absolute -top-20 -left-20 h-40 w-40 rounded-full opacity-60 blur-3xl"
               style={{ background: "var(--gradient-brand)" }} />
          <h1 className="text-2xl font-bold mb-1">Start learning</h1>
          <p className="text-sm text-muted-foreground mb-6">Create your EduPrep account</p>
          <form onSubmit={onSubmit} className="space-y-4">
            <Field icon={<User className="h-4 w-4" />} label="Name">
              <input required value={name} onChange={(e) => setName(e.target.value)}
                     className="w-full bg-transparent outline-none" placeholder="Your name" />
            </Field>
            <Field icon={<Mail className="h-4 w-4" />} label="Email">
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                     className="w-full bg-transparent outline-none" placeholder="you@uni.de" />
            </Field>
            <Field icon={<Lock className="h-4 w-4" />} label="Password">
              <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
                     className="w-full bg-transparent outline-none" placeholder="At least 8 characters" />
            </Field>
            <motion.button whileTap={{ scale: 0.97 }} whileHover={{ scale: 1.02 }} disabled={loading}
              className="relative w-full overflow-hidden rounded-xl py-3 font-semibold text-white glow-brand disabled:opacity-60"
              style={{ background: "var(--gradient-brand)" }}>
              {loading ? <Loader2 className="mx-auto h-5 w-5 animate-spin" /> : "Create account"}
            </motion.button>
          </form>
          <p className="mt-6 text-center text-sm text-muted-foreground">
            Already have an account? <Link to="/login" className="font-semibold text-foreground hover:underline">Sign in</Link>
          </p>
        </div>
      </motion.div>
    </div>
  );
}
