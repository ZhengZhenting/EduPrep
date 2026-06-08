import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CoursesAPI, PdfAPI, type CourseDetail, type PdfFile } from "../../lib/api";
import { ArrowLeft, FileText, Upload, Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/_authenticated/courses/$courseId")({ component: CourseDetail });

function CourseDetail() {
  const { courseId } = Route.useParams();
  const cid = Number(courseId);
  const navigate = useNavigate();
  const [course, setCourse] = useState<CourseDetail | null>(null);
  const [pdfs, setPdfs] = useState<PdfFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      // Bug 2 fix: GET /courses/{id} returns { id, title, pdf_files: [] } in one call
      const detail = await CoursesAPI.detail(cid);
      setCourse(detail);
      setPdfs(detail.pdf_files || []);
    } catch (e: any) {
      toast.error("Failed to load course");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [cid]);

  const handleFiles = async (files: FileList | null) => {
    if (!files || !files.length) return;
    setUploading(true);
    try {
      for (const f of Array.from(files)) {
        await PdfAPI.upload(f, cid);
        toast.success(`Uploaded ${f.name}`);
      }
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const remove = async (id: number) => {
    if (!confirm("Delete this PDF?")) return;
    try { await PdfAPI.remove(id); setPdfs((p) => p.filter((x) => x.id !== id)); }
    catch { toast.error("Delete failed"); }
  };

  return (
    <div>
      <Link to="/dashboard" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition">
        <ArrowLeft className="h-4 w-4" /> All courses
      </Link>
      <h1 className="mt-2 text-4xl font-bold tracking-tight">{course?.title || "Course"}</h1>
      <p className="mt-2 text-muted-foreground">Upload PDFs and open them to start the Preview → Learn → Quiz cycle.</p>

      {/* Upload zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files); }}
        className={`mt-8 group relative rounded-2xl border-2 border-dashed p-10 text-center transition cursor-pointer ${
          dragOver ? "border-primary bg-primary/5 glow-brand" : "border-black/[0.12] hover:border-black/[0.22] hover:bg-black/[0.02]"
        }`}
        onClick={() => inputRef.current?.click()}
      >
        <input ref={inputRef} type="file" accept="application/pdf" multiple className="hidden"
               onChange={(e) => handleFiles(e.target.files)} />
        {uploading ? (
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <div className="text-sm text-muted-foreground">Uploading & processing…</div>
          </div>
        ) : (
          <>
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl text-white"
                 style={{ background: "var(--gradient-brand)" }}>
              <Upload className="h-5 w-5" />
            </div>
            <div className="font-semibold">Drop PDFs here, or click to browse</div>
            <div className="mt-1 text-xs text-muted-foreground">German lecture slides work best</div>
          </>
        )}
      </div>

      {/* PDF list */}
      <div className="mt-8">
        <h2 className="mb-4 text-lg font-semibold">PDFs ({pdfs.length})</h2>
        {loading ? (
          <div className="grid gap-3 md:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-20 rounded-xl glass shimmer-bg" />)}
          </div>
        ) : pdfs.length === 0 ? (
          <div className="rounded-xl glass p-8 text-center text-sm text-muted-foreground">
            No PDFs yet. Upload one to start learning.
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            <AnimatePresence>
              {pdfs.map((p, i) => (
                <motion.div key={p.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }} transition={{ delay: i * 0.03 }}
                            whileHover={{ y: -2 }}
                            className="group relative glass-strong rounded-xl p-4 flex items-center gap-3 cursor-pointer hover:glow-brand transition"
                            onClick={() => navigate({ to: "/workspace/$courseId/$filename", params: { courseId: String(cid), filename: encodeURIComponent(p.filename) } })}>
                  <div className="flex h-11 w-11 items-center justify-center rounded-lg"
                       style={{ background: "linear-gradient(135deg, oklch(0.56 0.24 15), oklch(0.70 0.22 52))" }}>
                    <FileText className="h-5 w-5 text-white" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{p.filename}</div>
                    <div className="text-xs text-muted-foreground">Preview · Learn · Quiz</div>
                  </div>
                  <button onClick={(e) => { e.stopPropagation(); remove(p.id); }}
                          className="rounded-md p-1.5 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-destructive/30 hover:text-foreground transition">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  );
}
