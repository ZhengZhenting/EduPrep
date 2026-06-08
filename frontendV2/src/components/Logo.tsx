import { Sparkles } from "lucide-react";
import { Link } from "@tanstack/react-router";

export function Logo({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const text = size === "lg" ? "text-3xl" : size === "sm" ? "text-base" : "text-xl";
  return (
    <Link to="/" className="flex items-center gap-2 group">
      <div className="relative">
        <div className="absolute inset-0 blur-md opacity-60 group-hover:opacity-100 transition"
             style={{ background: "var(--gradient-brand)" }} />
        <div className="relative flex h-9 w-9 items-center justify-center rounded-xl"
             style={{ background: "var(--gradient-brand)" }}>
          <Sparkles className="h-4 w-4 text-white" />
        </div>
      </div>
      <span className={`${text} font-bold tracking-tight gradient-text`}>EduPrep</span>
    </Link>
  );
}
