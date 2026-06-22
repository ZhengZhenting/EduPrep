import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";

const BASE_URL =
  (typeof window !== "undefined" && (window as any).__API_URL__) ||
  import.meta.env.VITE_API_URL ||
  "http://localhost:8000";

const ACCESS_KEY = "eduprep_access_token";
const REFRESH_KEY = "eduprep_refresh_token";

export const tokenStore = {
  getAccess: () => (typeof window === "undefined" ? null : localStorage.getItem(ACCESS_KEY)),
  getRefresh: () => (typeof window === "undefined" ? null : localStorage.getItem(REFRESH_KEY)),
  set: (access: string, refresh?: string) => {
    localStorage.setItem(ACCESS_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear: () => {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

export const api = axios.create({ baseURL: BASE_URL });

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const t = tokenStore.getAccess();
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

let refreshing: Promise<string | null> | null = null;

async function refreshToken(): Promise<string | null> {
  const refresh = tokenStore.getRefresh();
  if (!refresh) return null;
  try {
    const res = await axios.post(`${BASE_URL}/auth/refresh`, { refresh_token: refresh });
    const access = res.data.access_token ?? res.data.accessToken;
    const newRefresh = res.data.refresh_token ?? res.data.refreshToken;
    if (access) {
      tokenStore.set(access, newRefresh);
      return access;
    }
  } catch {
    tokenStore.clear();
  }
  return null;
}

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      refreshing = refreshing ?? refreshToken();
      const newToken = await refreshing;
      refreshing = null;
      if (newToken) {
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      }
      if (typeof window !== "undefined") window.location.href = "/login";
    }
    return Promise.reject(error);
  },
);

// ---------- Typed API surface ----------
export type Course = { id: number; title: string; created_at?: string };
// Bug 2 fix: backend GET /courses/{id} returns { id, title, pdf_files: [] }
export type CourseDetail = { id: number; title: string; pdf_files: PdfFile[] };
export type PdfFile = { id: number; filename: string; course_id: number; created_at?: string };
export type VocabItem = { term: string; translation: string };
export type PreviewData = {
  summary_de?: string; summary_zh?: string;
  vocabulary?: VocabItem[];
  mermaid?: string;
  [k: string]: any;
};
export type ChatMsg = { role: "user" | "assistant"; content: string; sources?: any; source_type?: string };
// options is always normalized to string[] after API call (backend returns {A,B,C,D} object)
export type QuizQuestion = { question: string; options: string[]; answer: number; explanation?: string };
export type Note = { id: number; filename: string; type: string; content: string; created_at?: string };

// ---------- Quiz normalization (Bug 5) ----------
// Backend returns options as {A,B,C,D} object and answer as letter "A"/"B"/"C"/"D"
// Normalize to options: string[] and answer: number index
function normalizeQuizQuestions(raw: any[]): QuizQuestion[] {
  return raw.map((q: any) => {
    let options: string[];
    if (Array.isArray(q.options)) {
      options = q.options;
    } else {
      options = [q.options.A, q.options.B, q.options.C, q.options.D];
    }
    let answer: number;
    if (typeof q.answer === "number") {
      answer = q.answer;
    } else if (typeof q.answer === "string" && q.answer.length === 1) {
      answer = "ABCD".indexOf(q.answer.toUpperCase());
      if (answer === -1) answer = options.findIndex((o) => o === q.answer);
    } else {
      answer = options.findIndex((o) => o === q.answer);
    }
    return { ...q, options, answer } as QuizQuestion;
  });
}

export const AuthAPI = {
  register: (data: { email: string; name: string; password: string }) =>
    api.post("/auth/register", data).then((r) => r.data),
  login: (data: { email: string; password: string }) =>
    api.post("/auth/login", data).then((r) => r.data),
};

export const CoursesAPI = {
  // Bug 1 fix: backend returns { courses: [...] }, not a bare array
  list: (): Promise<Course[]> => api.get("/courses").then((r) => r.data.courses ?? r.data),
  // Bug 2 fix: use this to get course detail + pdf_files in one call
  detail: (id: number): Promise<CourseDetail> => api.get<CourseDetail>(`/courses/${id}`).then((r) => r.data),
  create: (title: string) => api.post<Course>("/courses", { title }).then((r) => r.data),
  rename: (id: number, title: string) => api.patch<Course>(`/courses/${id}`, { title }).then((r) => r.data),
  remove: (id: number) => api.delete(`/courses/${id}`).then((r) => r.data),
};

// Backend /upload returns immediately, then processes in a background thread.
// GET /upload/status/{filename} returns this shape while/after processing.
export type UploadStatus = {
  status: "processing" | "done" | "error";
  progress: number;
  chunks?: number;
  pdf_file_id?: number;
  message?: string;
};

export const PdfAPI = {
  upload: (file: File, courseId: number) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("course_id", String(courseId));
    return api.post("/upload", fd, { headers: { "Content-Type": "multipart/form-data" } }).then((r) => r.data);
  },
  status: (filename: string): Promise<UploadStatus> =>
    api.get(`/upload/status/${encodeURIComponent(filename)}`).then((r) => r.data),
  // Upload, then poll status until background processing is "done".
  // Throws on "error", or after timeoutMs (so it can never poll forever).
  uploadAndWait: async (
    file: File,
    courseId: number,
    opts?: { intervalMs?: number; timeoutMs?: number },
  ): Promise<UploadStatus> => {
    const intervalMs = opts?.intervalMs ?? 1500;
    const timeoutMs = opts?.timeoutMs ?? 5 * 60 * 1000; // 5 min cap
    await PdfAPI.upload(file, courseId);
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      await new Promise((res) => setTimeout(res, intervalMs));
      let s: UploadStatus;
      try {
        s = await PdfAPI.status(file.name);
      } catch {
        continue; // status row not ready yet / transient — keep polling until deadline
      }
      if (s.status === "done") return s;
      if (s.status === "error") throw new Error(s.message || "PDF processing failed");
    }
    throw new Error("Upload timed out while processing");
  },
  remove: (id: number) => api.delete(`/pdfs/${id}`).then((r) => r.data),
};

export const AIAPI = {
  preview: (filename: string, course_id: number) =>
    api.post<PreviewData>("/preview", { filename, course_id }).then((r) => r.data),
  ask: (data: { filename: string; course_id: number; question: string; history?: ChatMsg[] }) =>
    api.post("/ask", data).then((r) => r.data),
  // Bug 5 fix: normalize quiz options {A,B,C,D} → string[] and answer letter → index
  quiz: (filename: string, course_id: number, num_questions = 5): Promise<{ questions: QuizQuestion[] }> =>
    api.post("/quiz", { filename, course_id, num_questions }).then((r) => ({
      questions: normalizeQuizQuestions(r.data.questions ?? []),
    })),
  quizResult: (data: { filename: string; course_id: number; score: number; total: number }) =>
    api.post("/quiz/result", data).then((r) => r.data),
};

export const NotesAPI = {
  // Bug 4 fix: backend requires ?course_id= query param
  // Backend returns { filename, notes: [...] } — extract the notes array
  list: (filename: string, courseId: number): Promise<Note[]> =>
    api.get(`/notes/${encodeURIComponent(filename)}`, { params: { course_id: courseId } })
      .then((r) => r.data.notes ?? r.data ?? []),
  create: (data: { filename: string; course_id: number; type: string; content: string }) =>
    api.post("/notes", data).then((r) => r.data),
  remove: (id: number) => api.delete(`/notes/${id}`).then((r) => r.data),
};

export const MessagesAPI = {
  // Bug 3 fix: backend requires ?course_id= query param
  // Backend returns { filename, messages: [...] } — extract the messages array
  history: (filename: string, courseId: number): Promise<ChatMsg[]> =>
    api.get(`/message/${encodeURIComponent(filename)}`, { params: { course_id: courseId } })
      .then((r) => r.data.messages ?? r.data ?? []),
};
