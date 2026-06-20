import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import { AIAPI, NotesAPI, type PreviewData } from "../../lib/api";
import { Mermaid } from "./Mermaid";
import { BookmarkPlus, Loader2, Sparkles, Wand2 } from "lucide-react";
import { toast } from "sonner";

// Backend returns mindmap wrapped in ```mermaid fences — strip them.
function stripMermaidFence(raw?: string): string {
  if (!raw) return "";
  let s = raw.trim();
  if (s.startsWith("```")) { const lines = s.split("\n"); lines.shift(); s = lines.join("\n"); }
  if (s.includes("```")) { s = s.split("```")[0]; }
  s = s.trim();
  if (!s.startsWith("graph") && !s.startsWith("flowchart")) {
    const idx = s.search(/graph|flowchart/);
    if (idx !== -1) s = s.slice(idx);
  }
  return s.trim();
}

export function PreviewTab({ filename, courseId, onComplete }: { filename: string; courseId: number; onComplete?: () => void }) {
  const [data, setData] = useState<PreviewData | null>(null);
  // checkingCache = true while fetching notes to look for a cached preview
  const [checkingCache, setCheckingCache] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // On mount: look for a cached preview in the notes table (type="preview_cache").
  // This avoids re-generating every time the tab is opened.
  useEffect(() => {
    let live = true;
    NotesAPI.list(filename, courseId)
      .then((notes) => {
        if (!live) return;
        // Use the most recent preview_cache note (last in list = most recent by default)
        const cacheNotes = notes.filter((n) => n.type === "preview_cache");
        if (cacheNotes.length > 0) {
          const latest = cacheNotes[cacheNotes.length - 1];
          try {
            const cached = JSON.parse(latest.content);
            setData(cached);
            onComplete?.();
          } catch {
            // Corrupted cache entry — ignore, let user regenerate
          }
        }
      })
      .catch(() => {})
      .finally(() => { if (live) setCheckingCache(false); });
    return () => { live = false; };
    // eslint-disable-next-line
  }, [filename, courseId]);

  const generate = () => {
    setGenerating(true);
    setError(null);
    AIAPI.preview(filename, courseId)
      .then((d) => {
        setData(d);
        // Persist result to notes as "preview_cache" so next visit loads instantly
        NotesAPI.create({
          filename,
          course_id: courseId,
          type: "preview_cache",
          content: JSON.stringify(d),
        }).catch(() => {}); // non-blocking — don't break UI if cache save fails
        onComplete?.();
      })
      .catch((e: any) => {
        setError(e?.response?.data?.detail || "Failed to generate preview");
      })
      .finally(() => setGenerating(false));
  };

  const saveNote = async (type: string, content: string) => {
    try {
      await NotesAPI.create({ filename, course_id: courseId, type, content });
      toast.success("Saved to notes");
    } catch { toast.error("Save failed"); }
  };

  // ── State: checking for cached data ──────────────────────────────────────
  if (checkingCache) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground gap-2 text-sm">
        <Loader2 className="h-4 w-4 animate-spin" />
        Checking for saved preview…
      </div>
    );
  }

  // ── State: generating ─────────────────────────────────────────────────────
  if (generating) {
    return (
      <div className="space-y-4">
        {/* Loading banner at the TOP */}
        <div className="flex items-center gap-3 rounded-xl glass px-4 py-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin shrink-0 text-preview" />
          <span>Generating preview — bilingual summary, vocabulary and concept map…</span>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="h-48 rounded-2xl glass shimmer-bg" />
          <div className="h-48 rounded-2xl glass shimmer-bg" />
        </div>
        <div className="h-32 rounded-2xl glass shimmer-bg" />
        <div className="h-64 rounded-2xl glass shimmer-bg" />
      </div>
    );
  }

  // ── State: no data yet — show generate button ─────────────────────────────
  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        {error && (
          <div className="mb-6 rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive max-w-sm">
            {error}
          </div>
        )}
        <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl glow-preview"
             style={{ background: "var(--gradient-preview)" }}>
          <Sparkles className="h-8 w-8 text-white" />
        </div>
        <h2 className="text-xl font-bold mb-2">Ready to preview?</h2>
        <p className="text-sm text-muted-foreground mb-6 max-w-xs leading-relaxed">
          Generate a bilingual summary (DE + ZH), key vocabulary, and a concept map for this lecture.
        </p>
        <button onClick={generate}
                className="inline-flex items-center gap-2 rounded-xl px-6 py-3 font-semibold text-white glow-preview transition hover:scale-105"
                style={{ background: "var(--gradient-preview)" }}>
          <Wand2 className="h-4 w-4" /> Generate Preview
        </button>
      </div>
    );
  }

  // ── State: data available — show preview content ──────────────────────────
  const summaryDe = data.summary_de || data.summary?.de || data.de_summary;
  const summaryZh = data.summary_zh || data.summary?.zh || data.zh_summary;
  const vocab: string[] = data.vocabulary || data.vocab || [];
  const mermaidRaw = data.mindmap || data.mermaid || data.diagram;
  const mermaidChart = stripMermaidFence(mermaidRaw);

  return (
    <div className="space-y-6">
      {/* Summaries */}
      <div className="grid gap-4 md:grid-cols-2">
        {summaryDe && (
          <SummaryCard tag="Deutsch" content={summaryDe} accent="var(--gradient-preview)"
                       onSave={() => saveNote("summary", `# Deutsch\n\n${summaryDe}`)} delay={0} />
        )}
        {summaryZh && (
          <SummaryCard tag="中文" content={summaryZh} accent="linear-gradient(135deg, oklch(0.60 0.22 20), oklch(0.72 0.20 50))"
                       onSave={() => saveNote("summary", `# 中文\n\n${summaryZh}`)} delay={0.1} />
        )}
      </div>

      {/* Vocab */}
      {vocab.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
                    className="glass-strong rounded-2xl p-6">
          <div className="mb-4 flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <h3 className="font-semibold">Key vocabulary</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            {vocab.map((item: string, i: number) => (
              <div key={i}
                   className="rounded-full border border-black/[0.08] bg-black/[0.04] px-3 py-1.5 text-sm text-foreground cursor-default hover:bg-black/[0.07] transition">
                {item}
              </div>
            ))}
          </div>
          <button onClick={() => saveNote("vocabulary", vocab.map((v: string) => `- ${v}`).join("\n"))}
                  className="mt-4 inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
            <BookmarkPlus className="h-3.5 w-3.5" /> Save vocab to notes
          </button>
        </motion.div>
      )}

      {/* Diagram */}
      {mermaidChart && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
                    className="glass-strong rounded-2xl p-6">
          <h3 className="mb-4 font-semibold">Concept map</h3>
          <div className="rounded-xl bg-black/[0.04] p-4">
            <Mermaid chart={mermaidChart} />
          </div>
        </motion.div>
      )}
    </div>
  );
}

function SummaryCard({ tag, content, accent, onSave, delay }: { tag: string; content: string; accent: string; onSave: () => void; delay: number }) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }}
                className="group relative glass-strong rounded-2xl p-6 overflow-hidden">
      <div className="absolute top-0 left-0 h-1 w-full" style={{ background: accent }} />
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{tag}</span>
        <button onClick={onSave} className="opacity-0 group-hover:opacity-100 transition rounded-md p-1.5 hover:bg-black/[0.05]" title="Save to notes">
          <BookmarkPlus className="h-4 w-4" />
        </button>
      </div>
      <div className="prose prose-sm max-w-none">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    </motion.div>
  );
}
