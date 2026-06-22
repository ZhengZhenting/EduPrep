import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import { AIAPI, MessagesAPI, NotesAPI, type ChatMsg } from "../../lib/api";
import { Send, Loader2, Globe, FileText, BookmarkPlus, Sparkles, ExternalLink } from "lucide-react";
import { toast } from "sonner";

// ── Source parsing ────────────────────────────────────────────────────────────
// Live API response:  sources = { pages: [3, 7], urls: ["https://..."] }
// History from DB:    sources = ["https://..."]  (only URLs saved)
function parseSources(sources: any): { pages: number[]; urls: string[]; web_supplement: string } {
  if (!sources) return { pages: [], urls: [], web_supplement: "" };
  if (Array.isArray(sources)) {
    // From DB (legacy): array of URL strings
    return { pages: [], urls: sources.filter(Boolean), web_supplement: "" };
  }
  if (typeof sources === "object") {
    return {
      pages: Array.isArray(sources.pages) ? sources.pages : [],
      urls: Array.isArray(sources.urls) ? sources.urls.filter(Boolean) : [],
      web_supplement: typeof sources.web_supplement === "string" ? sources.web_supplement : "",
    };
  }
  return { pages: [], urls: [], web_supplement: "" };
}

function truncateUrl(url: string): string {
  try {
    const u = new URL(url);
    const path = u.pathname.length > 28 ? u.pathname.slice(0, 28) + "…" : u.pathname;
    return u.hostname + path;
  } catch {
    return url.length > 40 ? url.slice(0, 40) + "…" : url;
  }
}

// ── Page numbers footer (lecture / PDF part) ──────────────────────────────────
function PagesFooter({ sources }: { sources: any }) {
  const { pages } = parseSources(sources);
  if (pages.length === 0) return null;
  return (
    <div className="mt-2.5 pt-2 border-t border-black/[0.08] flex flex-wrap items-center gap-1.5">
      <FileText className="h-3 w-3 text-muted-foreground shrink-0" />
      {pages.map((p) => (
        <span key={p}
              className="rounded bg-black/[0.05] px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
          p.{p}
        </span>
      ))}
    </div>
  );
}

// ── Source URLs footer (web supplement part) ──────────────────────────────────
function UrlsFooter({ sources }: { sources: any }) {
  const { urls } = parseSources(sources);
  if (urls.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5">
      <Globe className="h-3 w-3 text-muted-foreground shrink-0" />
      {urls.map((url, i) => (
        <a key={i} href={url} target="_blank" rel="noopener noreferrer"
           className="inline-flex items-center gap-0.5 rounded bg-black/[0.05] px-1.5 py-0.5 text-[10px] text-muted-foreground hover:text-foreground hover:bg-black/[0.08] transition max-w-[220px]">
          <ExternalLink className="h-2.5 w-2.5 shrink-0" />
          <span className="truncate">{truncateUrl(url)}</span>
        </a>
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export function LearnTab({ filename, courseId, onActivity }: { filename: string; courseId: number; onActivity?: () => void }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    MessagesAPI.history(filename, courseId).then(setMessages).catch(() => {});
  }, [filename, courseId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  useEffect(() => { inputRef.current?.focus(); }, [filename]);

  const send = async () => {
    const q = input.trim();
    if (!q || sending) return;
    const userMsg: ChatMsg = { role: "user", content: q };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setSending(true);
    try {
      const res = await AIAPI.ask({ filename, course_id: courseId, question: q, history: messages });
      const answer = res.pdf_answer ?? res.answer ?? res.content ?? JSON.stringify(res);
      const sources = res.sources; // contains pages / urls / web_supplement
      const source_type = res.source_type ?? "pdf";
      setMessages((m) => [...m, { role: "assistant", content: answer, sources, source_type }]);
      onActivity?.();
    } catch (e: any) {
      setMessages((m) => [...m, { role: "assistant", content: `⚠️ ${e?.response?.data?.detail || "Request failed"}` }]);
    } finally {
      setSending(false);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  };

  const saveAnswer = async (content: string, sources?: any) => {
    const { web_supplement } = parseSources(sources);
    const full = web_supplement ? `${content}\n\n**网络补充：**\n${web_supplement}` : content;
    try { await NotesAPI.create({ filename, course_id: courseId, type: "answer", content: full }); toast.success("Saved to notes"); }
    catch { toast.error("Save failed"); }
  };

  return (
    <div className="glass-strong rounded-2xl flex flex-col h-[calc(100vh-18rem)] min-h-[520px] overflow-hidden">
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 && !sending && (
          <div className="h-full flex flex-col items-center justify-center text-center text-muted-foreground">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl text-white" style={{ background: "var(--gradient-learn)" }}>
              <Sparkles className="h-5 w-5" />
            </div>
            <p className="font-semibold text-foreground">Ask anything about this lecture</p>
            <p className="text-sm mt-1">Ich antworte auf Deutsch oder Englisch — try "Was sind die Hauptpunkte?"</p>
          </div>
        )}
        <AnimatePresence initial={false}>
          {messages.map((m, i) => (
            <motion.div key={i} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
                        className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`group max-w-[85%] rounded-2xl px-4 py-3 ${
                m.role === "user" ? "text-white" : "glass border border-black/[0.08]"
              }`} style={m.role === "user" ? { background: "var(--gradient-learn)" } : undefined}>

                {/* Message content */}
                <div className="prose prose-sm max-w-none">
                  <ReactMarkdown>{m.content}</ReactMarkdown>
                </div>

                {m.role === "assistant" && (
                  <>
                    {/* Part 1: lecture answer page numbers */}
                    <PagesFooter sources={m.sources} />

                    {/* Part 2: web supplement (only when present) */}
                    {(() => {
                      const { web_supplement } = parseSources(m.sources);
                      if (!web_supplement) return null;
                      return (
                        <div className="mt-3 pt-3 border-t border-black/[0.08]">
                          <div className="mb-1.5 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                            <Globe className="h-3 w-3" /> 网络补充
                          </div>
                          <div className="prose prose-sm max-w-none">
                            <ReactMarkdown>{web_supplement}</ReactMarkdown>
                          </div>
                          <UrlsFooter sources={m.sources} />
                        </div>
                      );
                    })()}

                    {/* Source type badge + Save button */}
                    <div className="mt-2 flex items-center justify-between gap-3">
                      {m.source_type && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-black/[0.05] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                          {m.source_type === "pdf+web" ? <Globe className="h-3 w-3" /> : <FileText className="h-3 w-3" />}
                          {m.source_type}
                        </span>
                      )}
                      <button onClick={() => saveAnswer(m.content, m.sources)}
                              className="opacity-0 group-hover:opacity-100 transition text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1 ml-auto">
                        <BookmarkPlus className="h-3 w-3" /> Save
                      </button>
                    </div>
                  </>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        {sending && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-start">
            <div className="glass rounded-2xl px-4 py-3 flex items-center gap-1">
              <Dot delay={0} /><Dot delay={0.15} /><Dot delay={0.3} />
            </div>
          </motion.div>
        )}
      </div>

      <div className="border-t border-black/[0.07] p-4">
        <div className="group flex items-end gap-2 rounded-2xl border border-black/[0.08] bg-black/[0.02] p-2 transition focus-within:border-learn focus-within:shadow-[0_0_0_4px_oklch(0.62_0.24_68/0.18)]">
          <textarea ref={inputRef} value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                    rows={1} placeholder="Ask about this lecture…"
                    className="flex-1 resize-none bg-transparent px-2 py-2 outline-none text-sm placeholder:text-muted-foreground max-h-32" />
          <button onClick={send} disabled={!input.trim() || sending}
                  className="flex h-9 w-9 items-center justify-center rounded-xl text-white disabled:opacity-40"
                  style={{ background: "var(--gradient-learn)" }}>
            {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </div>
  );
}

function Dot({ delay }: { delay: number }) {
  return <motion.span animate={{ y: [0, -4, 0], opacity: [0.4, 1, 0.4] }} transition={{ duration: 0.9, repeat: Infinity, delay }}
                      className="inline-block h-1.5 w-1.5 rounded-full bg-foreground/70 mx-0.5" />;
}
