import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AIAPI, type QuizQuestion } from "../../lib/api";
import { Check, X, Loader2, Trophy, RotateCcw, Sparkles, Wand2 } from "lucide-react";

export function QuizTab({ filename, courseId, onComplete }: { filename: string; courseId: number; onComplete?: () => void }) {
  const [questions, setQuestions] = useState<QuizQuestion[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [idx, setIdx] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);
  const [reveal, setReveal] = useState(false);
  const [wrongShake, setWrongShake] = useState(false);
  const [score, setScore] = useState(0);
  const [done, setDone] = useState(false);
  const [scoreAnim, setScoreAnim] = useState(0);

  const load = async () => {
    setLoading(true); setError(null);
    setQuestions(null); setIdx(0); setPicked(null); setReveal(false); setScore(0); setDone(false);
    try {
      const res = await AIAPI.quiz(filename, courseId, 5);
      const qs = res.questions || (res as any) || [];
      setQuestions(Array.isArray(qs) ? qs : []);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Failed to load quiz");
    } finally { setLoading(false); }
  };

  // No auto-generate on mount — user clicks the button to start.

  // ── State: not yet started ────────────────────────────────────────────────
  if (!questions && !loading && !error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl glow-quiz"
             style={{ background: "var(--gradient-quiz)" }}>
          <Trophy className="h-8 w-8 text-white" />
        </div>
        <h2 className="text-xl font-bold mb-2">Ready to test yourself?</h2>
        <p className="text-sm text-muted-foreground mb-6 max-w-xs leading-relaxed">
          Generate personalised multiple-choice questions based on this lecture and your weak concepts.
        </p>
        <button onClick={load}
                className="inline-flex items-center gap-2 rounded-xl px-6 py-3 font-semibold text-white glow-quiz transition hover:scale-105"
                style={{ background: "var(--gradient-quiz)" }}>
          <Wand2 className="h-4 w-4" /> Generate Quiz
        </button>
      </div>
    );
  }

  // ── State: loading ────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="glass-strong rounded-2xl p-12 text-center">
        <Loader2 className="mx-auto h-8 w-8 animate-spin text-quiz" />
        <p className="mt-3 text-sm text-muted-foreground">Generating quiz…</p>
      </div>
    );
  }

  // ── State: error ──────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center gap-4">
        <div className="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive max-w-sm">
          {error}
        </div>
        <button onClick={load}
                className="inline-flex items-center gap-2 rounded-xl px-5 py-2.5 font-semibold text-white glow-quiz"
                style={{ background: "var(--gradient-quiz)" }}>
          <RotateCcw className="h-4 w-4" /> Try again
        </button>
      </div>
    );
  }

  if (!questions || questions.length === 0) return <div className="rounded-xl glass p-6 text-sm">No questions returned.</div>;

  const q = questions[idx];
  // answer is always normalized to a number index by api.ts normalizeQuizQuestions()
  const correctIndex = q.answer;

  const submit = () => {
    if (picked === null) return;
    setReveal(true);
    if (picked === correctIndex) setScore((s) => s + 1);
    else setWrongShake(true);
    setTimeout(() => setWrongShake(false), 500);
  };

  const next = async () => {
    if (idx + 1 < questions.length) {
      setIdx(idx + 1); setPicked(null); setReveal(false);
    } else {
      setDone(true);
      // animate score counter
      let n = 0;
      const t = setInterval(() => {
        n++; setScoreAnim(n);
        if (n >= score) clearInterval(t);
      }, 90);
      try { await AIAPI.quizResult({ filename, course_id: courseId, score, total: questions.length }); } catch {}
      onComplete?.();
    }
  };

  if (done) {
    const pct = Math.round((score / questions.length) * 100);
    return (
      <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
                  className="glass-strong rounded-2xl p-12 text-center relative overflow-hidden">
        <div className="absolute inset-0 opacity-40 pulse-glow" style={{ background: "radial-gradient(circle at 50% 30%, oklch(0.56 0.24 15 / 0.35), transparent 60%)" }} />
        <div className="relative">
          <motion.div initial={{ rotate: -20, scale: 0 }} animate={{ rotate: 0, scale: 1 }} transition={{ type: "spring", damping: 12 }}
                      className="mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-3xl glow-quiz"
                      style={{ background: "var(--gradient-quiz)" }}>
            <Trophy className="h-10 w-10 text-white" />
          </motion.div>
          <div className="text-6xl font-bold gradient-text">{scoreAnim}/{questions.length}</div>
          <p className="mt-2 text-muted-foreground">{pct}% — {pct >= 80 ? "Sehr gut!" : pct >= 50 ? "Solid effort, review the gaps." : "Keep going — try another round."}</p>
          <button onClick={load}
                  className="mt-6 inline-flex items-center gap-2 rounded-xl px-5 py-2.5 font-semibold text-white glow-quiz"
                  style={{ background: "var(--gradient-quiz)" }}>
            <RotateCcw className="h-4 w-4" /> New quiz
          </button>
        </div>
      </motion.div>
    );
  }

  return (
    <div className="glass-strong rounded-2xl p-8 relative overflow-hidden">
      <div className="absolute top-0 left-0 h-1 w-full bg-black/[0.06]">
        <motion.div className="h-full" style={{ background: "var(--gradient-quiz)" }}
                    initial={{ width: 0 }} animate={{ width: `${(idx / questions.length) * 100}%` }} />
      </div>

      <div className="flex items-center justify-between text-xs text-muted-foreground mb-6">
        <span>Question {idx + 1} of {questions.length}</span>
        <span className="inline-flex items-center gap-1"><Sparkles className="h-3 w-3" /> Score {score}</span>
      </div>

      <AnimatePresence mode="wait">
        <motion.div key={idx} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}
                    className={wrongShake ? "shake" : ""}>
          <h2 className="text-2xl font-bold leading-snug mb-6">{q.question}</h2>
          <div className="space-y-3">
            {q.options.map((opt, i) => {
              const isPicked = picked === i;
              const isCorrect = i === correctIndex;
              let state: "default" | "picked" | "correct" | "wrong" = "default";
              if (reveal) {
                if (isCorrect) state = "correct";
                else if (isPicked) state = "wrong";
              } else if (isPicked) state = "picked";
              return (
                <motion.button key={i} disabled={reveal} onClick={() => setPicked(i)}
                  whileHover={!reveal ? { x: 4, scale: 1.01 } : {}}
                  className={`group flex w-full items-center justify-between gap-3 rounded-xl border px-5 py-4 text-left transition ${
                    state === "default" ? "border-black/[0.08] bg-black/[0.02] hover:border-black/[0.18]" :
                    state === "picked" ? "border-quiz bg-quiz/10" :
                    state === "correct" ? "border-emerald-500/60 bg-emerald-500/10 shadow-[0_0_30px_-5px_oklch(0.7_0.2_150/0.6)]" :
                    "border-destructive/60 bg-destructive/10"
                  }`}>
                  <span className="font-medium">{opt}</span>
                  {reveal && isCorrect && <Check className="h-5 w-5 text-emerald-400" />}
                  {reveal && !isCorrect && isPicked && <X className="h-5 w-5 text-destructive" />}
                </motion.button>
              );
            })}
          </div>

          {reveal && q.explanation && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                        className="mt-5 rounded-xl border border-black/[0.08] bg-black/[0.02] p-4 text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">Why: </span>{q.explanation}
            </motion.div>
          )}

          <div className="mt-6 flex justify-end">
            {!reveal ? (
              <button disabled={picked === null} onClick={submit}
                      className="rounded-xl px-5 py-2.5 font-semibold text-white disabled:opacity-40 glow-quiz"
                      style={{ background: "var(--gradient-quiz)" }}>Submit</button>
            ) : (
              <button onClick={next}
                      className="rounded-xl px-5 py-2.5 font-semibold text-white glow-quiz"
                      style={{ background: "var(--gradient-quiz)" }}>
                {idx + 1 < questions.length ? "Next question" : "See results"}
              </button>
            )}
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
