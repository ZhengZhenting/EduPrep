// Separated from auth.tsx so Vite Fast Refresh works correctly.
// auth.tsx exports only AuthProvider (component); this file exports only useAuth (hook).
import { useContext } from "react";
import { Ctx } from "./auth";

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used within AuthProvider");
  return v;
}
