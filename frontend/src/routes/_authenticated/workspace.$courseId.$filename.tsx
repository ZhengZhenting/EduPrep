import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowLeft, FileText, StickyNote, X } from "lucide-react";
import { CoursesAPI, type PdfFile } from "../../lib/api";
import { PreviewTab } from "../../components/workspace/PreviewTab";
import { LearnTab } from "../../components/workspace/LearnTab";
import { QuizTab } from "../../components/workspace/QuizTab";
import { NotesPanel } from "../../components/workspace/NotesPanel";

export const Route = createFileRoute("/_authenticated/workspace/$courseId/$filename")({
  component: Workspace,
});

type TabKey = "preview" | "learn" | "quiz";

function Workspace() {
  const { courseId, filename } = Route.useParams();
  const cid = Number(courseId);
  const fname = decodeURIComponent(filename);

  const [tab, setTab] = useState<TabKey>("preview");
  const [pdfs, setPdfs] = useState<PdfFile[]>([]);
  const [notesOpen, setNotesOpen] = useState(false);

  // progress
  const progressKey = `eduprep_progress_${cid}_${fname}`;
  const [progress, setProgress] = useState<Record<TabKey, boolean>>({ preview: false, learn: false, quiz: false });
  useEffect(() => {
    const raw = localStorage.getItem(progressKey);
    if (raw) setProgress(JSON.parse(raw));
  }, [progressKey]);
  const markDone = (k: TabKey) => {
    setProgress((p) => {
      const n = { ...p, [k]: true };
      localStorage.setItem(progressKey, JSON.stringify(n));
      return n;
    });
  };

  useEffect(() => {
    // Bug 2 fix: use GET /courses/{id} which returns { id, title, pdf_files: [] }
    CoursesAPI.detail(cid)
      .then((d) => setPdfs(d.pdf_files || []))
      .catch(() => {});
  }, [cid]);

  const completed = (Object.values(progress).filter(Boolean).length / 3) * 100;

  return (
    <div className="flex gap-6 -mx-2">
      {/* Sidebar */}
      <aside className="hidden lg:flex w-72 shrink-0 flex-col gap-4 sticky top-24 self-start max-h-[calc(100vh-7rem)]">
        <Link to="/courses/$courseId" params={{ courseId }} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> Back to course
        </Link>

        <div className="glass-strong rounded-2xl p-4">
          <div className="text-xs uppercase tracking-wider text-muted-foreground mb-3">PDFs in course</div>
          <div className="flex flex-col gap-1 max-h-72 overflow-y-auto pr-1">
            {pdfs.map((p) => {
              const active = p.filename === fname;
              return (
                <Link key={p.id}
                      to="/workspace/$courseId/$filename"
                      params={{ courseId, filename: encodeURIComponent(p.filename) }}
                      className={`flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm transition ${
                        active ? "bg-black/[0.07] text-foreground" : "text-muted-foreground hover:bg-black/[0.04] hover:text-foreground"
                      }`}>
                  <FileText className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{p.filename}</span>
                </Link>
              );
            })}
          </div>
        </div>

        <button onClick={() => setNotesOpen(true)}
                className="glass-strong rounded-2xl p-4 flex items-center gap-3 text-left hover:glow-brand transition">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-black/[0.06]">
            <StickyNote className="h-4 w-4" />
          </div>
          <div>
            <div className="font-semibold text-sm">My notes</div>
            <div className="text-xs text-muted-foreground">Saved highlights from this PDF</div>
          </div>
        </button>
      </aside>

      {/* Main */}
      <div className="flex-1 min-w-0">
        <div className="mb-4">
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight truncate">{fname}</h1>
          <div className="mt-3 flex items-center gap-3">
            <div className="h-1.5 flex-1 max-w-xs overflow-hidden rounded-full bg-black/[0.07]">
              <motion.div className="h-full rounded-full" style={{ background: "var(--gradient-brand)" }}
                          initial={{ width: 0 }} animate={{ width: `${completed}%` }} transition={{ duration: 0.6 }} />
            </div>
            <span className="text-xs text-muted-foreground">{Math.round(completed)}% complete</span>
          </div>
        </div>

        {/* Tabs */}
        <div className="glass-strong rounded-2xl p-1.5 inline-flex relative mb-6">
          {(["preview", "learn", "quiz"] as TabKey[]).map((k) => {
            const active = tab === k;
            const gradient = k === "preview" ? "var(--gradient-preview)" : k === "learn" ? "var(--gradient-learn)" : "var(--gradient-quiz)";
            return (
              <button key={k} onClick={() => setTab(k)}
                      className={`relative z-10 px-5 py-2 rounded-xl text-sm font-semibold capitalize transition ${active ? "text-white" : "text-muted-foreground hover:text-foreground"}`}>
                {active && (
                  <motion.div layoutId="tab-pill" className="absolute inset-0 rounded-xl -z-10"
                              style={{ background: gradient }}
                              transition={{ type: "spring", stiffness: 400, damping: 30 }} />
                )}
                {k}
                {progress[k] && <span className="ml-1.5 text-[10px]">✓</span>}
              </button>
            );
          })}
        </div>

        <AnimatePresence mode="wait">
          <motion.div key={tab}
                      initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.25 }}>
            {tab === "preview" && <PreviewTab filename={fname} courseId={cid} onComplete={() => markDone("preview")} />}
            {tab === "learn" && <LearnTab filename={fname} courseId={cid} onActivity={() => markDone("learn")} />}
            {tab === "quiz" && <QuizTab filename={fname} courseId={cid} onComplete={() => markDone("quiz")} />}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Notes drawer */}
      <AnimatePresence>
        {notesOpen && (
          <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        onClick={() => setNotesOpen(false)}
                        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm" />
            <motion.aside initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
                          transition={{ type: "spring", damping: 28, stiffness: 260 }}
                          className="fixed right-0 top-0 z-50 h-full w-full max-w-md glass-strong border-l border-black/[0.08] p-6 overflow-y-auto">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold">Notes</h2>
                <button onClick={() => setNotesOpen(false)} className="rounded-lg p-2 hover:bg-black/[0.05]"><X className="h-4 w-4" /></button>
              </div>
              <NotesPanel filename={fname} courseId={cid} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
