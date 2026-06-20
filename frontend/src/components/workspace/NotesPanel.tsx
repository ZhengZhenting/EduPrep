import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { NotesAPI, type Note } from "../../lib/api";
import { Trash2, Loader2, StickyNote } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { toast } from "sonner";

export function NotesPanel({ filename, courseId }: { filename: string; courseId: number }) {
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const all = await NotesAPI.list(filename, courseId);
      // Filter out "preview_cache" entries — those are internal cache, not user notes
      setNotes(all.filter((n) => n.type !== "preview_cache"));
    }
    catch { /* empty fine */ }
    finally { setLoading(false); }
  };
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [filename, courseId]);

  const create = async () => {
    if (!draft.trim()) return;
    setSaving(true);
    try {
      await NotesAPI.create({ filename, course_id: courseId, type: "custom", content: draft.trim() });
      setDraft("");
      await refresh();
      toast.success("Note added");
    } catch { toast.error("Save failed"); }
    finally { setSaving(false); }
  };

  const remove = async (id: number) => {
    try { await NotesAPI.remove(id); setNotes((n) => n.filter((x) => x.id !== id)); }
    catch { toast.error("Delete failed"); }
  };

  return (
    <div className="space-y-4">
      <div className="glass rounded-xl p-3">
        <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={3}
                  placeholder="Write a quick note (markdown supported)…"
                  className="w-full resize-none bg-transparent text-sm outline-none placeholder:text-muted-foreground" />
        <div className="flex justify-end">
          <button onClick={create} disabled={!draft.trim() || saving}
                  className="rounded-lg px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                  style={{ background: "var(--gradient-brand)" }}>
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "Add note"}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-6"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
      ) : notes.length === 0 ? (
        <div className="text-center py-10 text-muted-foreground text-sm">
          <StickyNote className="mx-auto h-6 w-6 mb-2 opacity-50" />
          No notes yet for this PDF.
        </div>
      ) : (
        <div className="space-y-3">
          <AnimatePresence>
            {notes.map((n) => (
              <motion.div key={n.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: 20 }}
                          className="group glass rounded-xl p-3 relative">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{n.type}</span>
                  <button onClick={() => remove(n.id)}
                          className="opacity-0 group-hover:opacity-100 transition rounded p-1 hover:bg-destructive/30">
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
                <div className="prose prose-sm max-w-none">
                  <ReactMarkdown>{n.content}</ReactMarkdown>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
