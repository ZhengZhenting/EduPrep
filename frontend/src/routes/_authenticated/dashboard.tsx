import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CoursesAPI, type Course } from "../../lib/api";
import { Plus, BookOpen, Trash2, Pencil, Loader2 } from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_authenticated/dashboard")({ component: Dashboard });

function Dashboard() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const refresh = async () => {
    setLoading(true);
    try { setCourses(await CoursesAPI.list()); }
    catch (e: any) { toast.error(e?.response?.data?.detail || "Failed to load courses"); }
    finally { setLoading(false); }
  };
  useEffect(() => { refresh(); }, []);

  const handleCreate = async () => {
    if (!newTitle.trim()) return;
    try {
      const c = await CoursesAPI.create(newTitle.trim());
      setCourses((cs) => [c, ...cs]);
      setNewTitle(""); setCreating(false);
      toast.success("Course created");
    } catch (e: any) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const handleRename = async (id: number) => {
    if (!editTitle.trim()) return;
    try {
      const u = await CoursesAPI.rename(id, editTitle.trim());
      setCourses((cs) => cs.map((c) => (c.id === id ? { ...c, ...u } : c)));
      setEditId(null);
    } catch (e: any) { toast.error("Rename failed"); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this course and all its PDFs?")) return;
    try {
      await CoursesAPI.remove(id);
      setCourses((cs) => cs.filter((c) => c.id !== id));
      toast.success("Deleted");
    } catch { toast.error("Delete failed"); }
  };

  return (
    <div>
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                  className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="text-4xl font-bold tracking-tight">Your courses</h1>
          <p className="mt-2 text-muted-foreground">Pick a course or start a new learning journey.</p>
        </div>
        <button onClick={() => setCreating(true)}
                className="group relative inline-flex items-center gap-2 overflow-hidden rounded-xl px-4 py-2.5 text-sm font-semibold text-white glow-brand transition hover:scale-105"
                style={{ background: "var(--gradient-brand)" }}>
          <Plus className="h-4 w-4" /> New course
        </button>
      </motion.div>

      <AnimatePresence>
        {creating && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                      className="mb-6 overflow-hidden">
            <div className="glass-strong rounded-2xl p-4 flex gap-2">
              <input autoFocus value={newTitle} onChange={(e) => setNewTitle(e.target.value)}
                     onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                     placeholder="Course title (e.g. Maschinelles Lernen WS25)"
                     className="flex-1 rounded-lg bg-black/[0.04] px-4 py-2.5 outline-none border border-black/[0.08] focus:border-primary/60" />
              <button onClick={handleCreate} className="rounded-lg px-4 py-2.5 font-semibold text-white" style={{ background: "var(--gradient-brand)" }}>Create</button>
              <button onClick={() => { setCreating(false); setNewTitle(""); }} className="rounded-lg px-4 py-2.5 text-muted-foreground hover:bg-black/[0.05]">Cancel</button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {loading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-44 rounded-2xl glass shimmer-bg" />
          ))}
        </div>
      ) : courses.length === 0 ? (
        <EmptyState onCreate={() => setCreating(true)} />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {courses.map((c, i) => (
            <motion.div key={c.id} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.05 }}
                        whileHover={{ y: -4 }}
                        className="group relative">
              <Link to="/courses/$courseId" params={{ courseId: String(c.id) }}
                    className="block glass-strong rounded-2xl p-6 transition hover:glow-brand">
                <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl text-white"
                     style={{ background: "var(--gradient-brand)" }}>
                  <BookOpen className="h-6 w-6" />
                </div>
                {editId === c.id ? (
                  <input autoFocus value={editTitle} onChange={(e) => setEditTitle(e.target.value)}
                         onClick={(e) => e.preventDefault()}
                         onBlur={() => handleRename(c.id)}
                         onKeyDown={(e) => { if (e.key === "Enter") handleRename(c.id); if (e.key === "Escape") setEditId(null); }}
                         className="w-full rounded-md bg-black/[0.04] px-2 py-1 outline-none border border-black/[0.08]" />
                ) : (
                  <h3 className="text-lg font-semibold leading-tight">{c.title}</h3>
                )}
                <p className="mt-1 text-xs text-muted-foreground">Open course →</p>
              </Link>
              <div className="absolute top-4 right-4 flex gap-1 opacity-0 group-hover:opacity-100 transition">
                <button onClick={() => { setEditId(c.id); setEditTitle(c.title); }}
                        className="rounded-md bg-white/75 p-1.5 hover:bg-black/[0.08] border border-black/[0.06]"><Pencil className="h-3.5 w-3.5" /></button>
                <button onClick={() => handleDelete(c.id)}
                        className="rounded-md bg-white/75 p-1.5 hover:bg-destructive/20 border border-black/[0.06]"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="glass-strong relative overflow-hidden rounded-2xl p-12 text-center">
      <div className="absolute inset-0 opacity-30" style={{ background: "var(--gradient-app)" }} />
      <div className="relative">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl text-white glow-brand"
             style={{ background: "var(--gradient-brand)" }}>
          <BookOpen className="h-8 w-8" />
        </div>
        <h2 className="text-2xl font-bold">No courses yet</h2>
        <p className="mt-2 text-muted-foreground">Create your first course and start uploading lecture PDFs.</p>
        <button onClick={onCreate} className="mt-6 rounded-xl px-5 py-2.5 font-semibold text-white glow-brand"
                style={{ background: "var(--gradient-brand)" }}>Create a course</button>
      </div>
    </div>
  );
}
