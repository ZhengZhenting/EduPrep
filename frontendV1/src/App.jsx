import { useState, useEffect, useRef } from 'react'
import AnswerRenderer from './AnswerRenderer'

// ─── Global Style ─────────────────────────────────────────────────────────────
function GlobalStyle() {
  return (
    <style>{`
      @import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600;9..40,700&display=swap');
      *, *::before, *::after { box-sizing: border-box; }
      html, body {
        margin: 0; padding: 0; min-height: 100vh;
        font-family: 'DM Sans', system-ui, sans-serif;
        background: #FAF7F2;
      }
      ::-webkit-scrollbar { width: 4px; }
      ::-webkit-scrollbar-track { background: transparent; }
      ::-webkit-scrollbar-thumb { background: rgba(45,42,255,0.25); border-radius: 4px; }
    `}</style>
  )
}

const API = 'http://localhost:8000'

const getToken = () => localStorage.getItem('edu_token')
const saveToken = t => localStorage.setItem('edu_token', t)
const removeToken = () => localStorage.removeItem('edu_token')

const saveUserData = u => localStorage.setItem('edu_user', JSON.stringify(u))
const getUserData = () => { try { return JSON.parse(localStorage.getItem('edu_user')) } catch { return null } }
const removeUserData = () => localStorage.removeItem('edu_user')

const authFetch = async (url, options = {}) => {
  const token = getToken()
  const res = await fetch(url, {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    }
  })
  if (res.status === 401) {
    removeToken()
    window.location.reload()
  }
  return res
}

// ─── Auth Screen ──────────────────────────────────────────────────────────────
function AuthScreen({ onLogin }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async () => {
    setError('')
    setLoading(true)
    try {
      if (mode === 'login') {
        const res = await fetch(`${API}/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password })
        })
        if (!res.ok) throw new Error((await res.json()).detail || 'Login failed')
        const data = await res.json()
        saveToken(data.access_token)
        onLogin(data.user)
      } else {
        const res = await fetch(`${API}/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, name, password })
        })
        if (!res.ok) throw new Error((await res.json()).detail || 'Registration failed')
        const loginRes = await fetch(`${API}/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password })
        })
        const data = await loginRes.json()
        saveToken(data.access_token)
        onLogin(data.user)
      }
    } catch (err) {
      setError(err.message)
    }
    setLoading(false)
  }

  return (
    <div style={s.authBg}>
      <div style={s.authCard}>
        <div style={s.authLogo}>EduPrep</div>
        <p style={s.authSubtitle}>
          {mode === 'login' ? 'Sign in to your knowledge space' : 'Create your account'}
        </p>
        {mode === 'register' && (
          <input style={s.authInput} placeholder="Full name" value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSubmit()} />
        )}
        <input style={s.authInput} placeholder="Email" type="email" value={email}
          onChange={e => setEmail(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSubmit()} />
        <input style={s.authInput} placeholder="Password" type="password" value={password}
          onChange={e => setPassword(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSubmit()} />
        {error && <p style={s.authError}>{error}</p>}
        <button style={loading ? s.authBtnDisabled : s.authBtn} onClick={handleSubmit} disabled={loading}>
          {loading ? '...' : mode === 'login' ? 'Sign in' : 'Create account'}
        </button>
        <p style={s.authToggle}>
          {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
          <span style={s.authToggleLink} onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}>
            {mode === 'login' ? 'Register' : 'Sign in'}
          </span>
        </p>
      </div>
    </div>
  )
}

// ─── Sidebar ──────────────────────────────────────────────────────────────────
function Sidebar({ user, selectedCourse, selectedPdf, onSelectCourse, onSelectPdf, onGoHome, onLogout, refreshKey }) {
  const [courses, setCourses] = useState([])
  const [expandedId, setExpandedId] = useState(null)
  const [pdfMap, setPdfMap] = useState({})
  const [loadingPdfs, setLoadingPdfs] = useState({})
  const expandedIdRef = useRef(null)

  const setExpanded = (id) => {
    expandedIdRef.current = id
    setExpandedId(id)
  }

  useEffect(() => {
    loadCourses()
    if (expandedIdRef.current) refreshPdfs(expandedIdRef.current)
  }, [refreshKey])

  useEffect(() => {
    if (selectedCourse?.id) {
      setExpanded(selectedCourse.id)
      refreshPdfs(selectedCourse.id)
    }
  }, [selectedCourse])

  const loadCourses = async () => {
    try {
      const res = await authFetch(`${API}/courses`)
      const data = await res.json()
      setCourses(data.courses || [])
    } catch (err) { console.error(err) }
  }

  const toggleCourse = async (course) => {
    const isOpen = expandedId === course.id
    setExpanded(isOpen ? null : course.id)
    if (!isOpen) {
      onSelectCourse(course)
      setLoadingPdfs(prev => ({ ...prev, [course.id]: true }))
      try {
        const res = await authFetch(`${API}/courses/${course.id}`)
        const data = await res.json()
        setPdfMap(prev => ({ ...prev, [course.id]: data.pdf_files || [] }))
      } catch (err) { console.error(err) }
      setLoadingPdfs(prev => ({ ...prev, [course.id]: false }))
    }
  }

  const refreshPdfs = async (courseId) => {
    try {
      const res = await authFetch(`${API}/courses/${courseId}`)
      const data = await res.json()
      setPdfMap(prev => ({ ...prev, [courseId]: data.pdf_files || [] }))
    } catch (err) { console.error(err) }
  }

  return (
    <div style={s.sidebar}>
      <div style={s.sidebarLogo} onClick={onGoHome}>EduPrep</div>

      <nav style={s.sidebarNav}>
        <p style={s.sidebarSection}>COURSES</p>
        {courses.map(c => (
          <div key={c.id}>
            {/* Course row */}
            <div
              style={{ ...s.sidebarCourseRow, ...(selectedCourse?.id === c.id && expandedId === c.id ? s.sidebarCourseRowActive : {}) }}
              onClick={() => toggleCourse(c)}
            >
              <span style={s.sidebarChevron}>{expandedId === c.id ? '▾' : '▸'}</span>
              <span style={s.sidebarCourseName}>{c.title}</span>
              <span style={s.sidebarPdfCount}>{c.pdf_count}</span>
            </div>

            {/* PDF sub-items */}
            {expandedId === c.id && (
              <div>
                {loadingPdfs[c.id] && (
                  <p style={s.sidebarPdfLoading}>Loading...</p>
                )}
                {(pdfMap[c.id] || []).map(pdf => (
                  <div
                    key={pdf.id}
                    style={{ ...s.sidebarPdfItem, ...(selectedPdf === pdf.filename ? s.sidebarPdfItemActive : {}) }}
                    onClick={() => onSelectPdf(c, pdf.filename)}
                  >
                    <span style={{ ...s.sidebarPdfDot, ...(selectedPdf === pdf.filename ? { color: ink } : {}) }}>·</span>
                    <span style={{ ...s.sidebarPdfName, ...(selectedPdf === pdf.filename ? { color: ink, fontWeight: 600 } : {}) }}>{pdf.filename.replace('.pdf', '')}</span>
                  </div>
                ))}
                {!loadingPdfs[c.id] && (pdfMap[c.id] || []).length === 0 && (
                  <p style={s.sidebarPdfLoading}>No PDFs yet</p>
                )}
              </div>
            )}
          </div>
        ))}
      </nav>

      <div style={s.sidebarFooter}>
        <div style={s.sidebarUserRow}>
          <span style={s.sidebarUserIcon}>◎</span>
          <span style={s.sidebarUserName}>{user?.name || user?.email || 'User'}</span>
        </div>
        <button style={s.sidebarLogout} onClick={onLogout}>
          <span style={s.sidebarLogoutIcon}>⏻</span>
          Sign out
        </button>
      </div>
    </div>
  )
}

// ─── Courses View ─────────────────────────────────────────────────────────────
function CoursesView({ onSelectCourse }) {
  const [courses, setCourses] = useState([])
  const [loading, setLoading] = useState(true)
  const [newTitle, setNewTitle] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [creating, setCreating] = useState(false)
  const [hoveredId, setHoveredId] = useState(null)

  useEffect(() => { loadCourses() }, [])

  const loadCourses = async () => {
    setLoading(true)
    try {
      const res = await authFetch(`${API}/courses`)
      const data = await res.json()
      setCourses(data.courses || [])
    } catch (err) { console.error(err) }
    setLoading(false)
  }

  const createCourse = async () => {
    if (!newTitle.trim()) return
    setCreating(true)
    try {
      const res = await authFetch(`${API}/courses`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle.trim() })
      })
      if (!res.ok) throw new Error('Create failed')
      setNewTitle('')
      setShowForm(false)
      await loadCourses()
    } catch (err) { alert(err.message) }
    setCreating(false)
  }

  const deleteCourse = async (e, id) => {
    e.stopPropagation()
    if (!confirm('Delete this course and all its PDFs?')) return
    try {
      await authFetch(`${API}/courses/${id}`, { method: 'DELETE' })
      await loadCourses()
    } catch (err) { alert(err.message) }
  }

  if (loading) return <p style={s.loadingText}>Loading...</p>

  return (
    <div>
      <div style={s.pageHeader}>
        <h1 style={s.pageTitle}>Your Courses</h1>
        <button style={s.textBtn} onClick={() => setShowForm(!showForm)}>+ New Course</button>
      </div>

      {showForm && (
        <div style={s.createForm}>
          <input style={s.createInput} placeholder="Course title..." value={newTitle}
            onChange={e => setNewTitle(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && createCourse()} autoFocus />
          <button style={creating ? s.authBtnDisabled : s.actionBtn} onClick={createCourse} disabled={creating}>
            {creating ? '...' : 'Create'}
          </button>
          <button style={s.cancelBtn} onClick={() => setShowForm(false)}>Cancel</button>
        </div>
      )}

      {courses.length === 0 ? (
        <div style={s.emptyState}>
          <p style={s.emptyText}>No courses yet. Create your first course to begin.</p>
        </div>
      ) : (
        <div style={s.courseGrid}>
          {courses.map((c, i) => (
            <div key={c.id}
              style={{ ...s.courseCard, background: cardPalette[i % 4], borderColor: cardBorderPalette[i % 4], ...(hoveredId === c.id ? s.courseCardHover : {}) }}
              onClick={() => onSelectCourse(c)}
              onMouseEnter={() => setHoveredId(c.id)}
              onMouseLeave={() => setHoveredId(null)}>
              <h2 style={s.courseCardTitle}>{c.title}</h2>
              <p style={s.courseCardMeta}>{c.pdf_count} document{c.pdf_count !== 1 ? 's' : ''}</p>
              <button style={s.cardDeleteBtn} onClick={e => deleteCourse(e, c.id)}>×</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Course Detail ────────────────────────────────────────────────────────────
function CourseDetailView({ course, onSelectPdf, onBack, onUploadDone }) {
  const [pdfs, setPdfs] = useState([])
  const [uploading, setUploading] = useState(false)
  const [uploadStatus, setUploadStatus] = useState('')
  const [dragging, setDragging] = useState(false)
  const fileRef = useRef(null)

  useEffect(() => { loadPdfs() }, [course.id])

  const loadPdfs = async () => {
    try {
      const res = await authFetch(`${API}/courses/${course.id}`)
      const data = await res.json()
      setPdfs(data.pdf_files || [])
    } catch (err) { console.error(err) }
  }

  const handleUpload = async (file) => {
    if (!file || !file.name.endsWith('.pdf')) { alert('Please select a PDF file'); return }
    setUploading(true)
    setUploadStatus('Uploading...')
    const formData = new FormData()
    formData.append('file', file)
    formData.append('course_id', course.id)
    try {
      const res = await authFetch(`${API}/upload`, { method: 'POST', body: formData })
      const data = await res.json()
      setUploadStatus('Processing PDF...')
      pollStatus(data.filename)
    } catch (err) {
      setUploadStatus(`Upload failed: ${err.message}`)
      setUploading(false)
    }
  }

  const pollStatus = (filename) => {
    const iv = setInterval(async () => {
      try {
        const res = await authFetch(`${API}/upload/status/${encodeURIComponent(filename)}`)
        const data = await res.json()
        if (data.status === 'done') {
          clearInterval(iv)
          setUploadStatus(`Ready — ${data.chunks} chunks processed`)
          setUploading(false)
          await loadPdfs()
          if (onUploadDone) onUploadDone()
        } else if (data.status === 'error') {
          clearInterval(iv)
          setUploadStatus(`Error: ${data.message}`)
          setUploading(false)
        } else {
          setUploadStatus(`Processing... ${data.progress}%`)
        }
      } catch { clearInterval(iv); setUploading(false) }
    }, 2000)
  }

  return (
    <div>
      <button style={s.backBtn} onClick={onBack}>← Courses</button>
      <h1 style={s.pageTitle}>{course.title}</h1>

      <div
        style={{ ...s.uploadZone, ...(dragging ? s.uploadZoneDrag : {}) }}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => { e.preventDefault(); setDragging(false); handleUpload(e.dataTransfer.files[0]) }}
        onClick={() => !uploading && fileRef.current?.click()}>
        <input ref={fileRef} type="file" accept=".pdf" style={{ display: 'none' }}
          onChange={e => e.target.files[0] && handleUpload(e.target.files[0])} />
        {uploading ? (
          <>
            <p style={s.uploadLabel}>{uploadStatus}</p>
            <div style={s.progressBg}><div style={{ ...s.progressFill, width: '60%' }} /></div>
          </>
        ) : (
          <>
            <div style={s.uploadIcon}>↑</div>
            <p style={s.uploadLabel}>Drop a PDF here or click to upload</p>
            {uploadStatus && <p style={s.uploadStatusText}>{uploadStatus}</p>}
          </>
        )}
      </div>

      {pdfs.length > 0 && (
        <>
          <h2 style={s.sectionTitle}>Documents</h2>
          <div style={s.pdfList}>
            {pdfs.map(pdf => (
              <div key={pdf.id} style={s.pdfItem}>
                <div style={s.pdfIcon} onClick={() => onSelectPdf(pdf.filename)}>PDF</div>
                <div style={s.pdfInfo} onClick={() => onSelectPdf(pdf.filename)}>
                  <p style={s.pdfName}>{pdf.filename}</p>
                  <p style={s.pdfMeta}>{pdf.chunk_count} chunks · {new Date(pdf.created_at).toLocaleDateString()}</p>
                </div>
                <button style={s.pdfDeleteBtn} onClick={async (e) => {
                  e.stopPropagation()
                  if (!confirm(`Delete "${pdf.filename}"? This cannot be undone.`)) return
                  try {
                    const res = await authFetch(`${API}/pdfs/${pdf.id}`, { method: 'DELETE' })
                    if (!res.ok) throw new Error((await res.json()).detail)
                    await loadPdfs()
                  } catch (err) { alert(err.message) }
                }}>×</button>
                <span style={s.pdfArrow} onClick={() => onSelectPdf(pdf.filename)}>→</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ─── Learn View ───────────────────────────────────────────────────────────────
function LearnView({ filename, courseId, onBack }) {
  const [mode, setMode] = useState(null)

  // Preview
  const [previewData, setPreviewData] = useState(null)
  const [previewing, setPreviewing] = useState(false)

  // Learn
  const [question, setQuestion] = useState('')
  const [history, setHistory] = useState([])
  const [asking, setAsking] = useState(false)

  // Quiz
  const [quizQuestions, setQuizQuestions] = useState([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [selectedOption, setSelectedOption] = useState(null)
  const [showResult, setShowResult] = useState(false)
  const [score, setScore] = useState(0)
  const [quizFinished, setQuizFinished] = useState(false)
  const [loadingQuiz, setLoadingQuiz] = useState(false)

  // Notes
  const [notes, setNotes] = useState([])
  const [showNotes, setShowNotes] = useState(false)

  useEffect(() => {
    loadMessages()
    loadNotes()
  }, [filename])

  const loadMessages = async () => {
    try {
      const res = await authFetch(`${API}/message/${encodeURIComponent(filename)}?course_id=${courseId}`)
      if (!res.ok) return
      const data = await res.json()
      if (data.messages?.length > 0) setHistory(data.messages)
    } catch (err) { console.error(err) }
  }

  const loadNotes = async () => {
    try {
      const res = await authFetch(`${API}/notes/${encodeURIComponent(filename)}?course_id=${courseId}`)
      if (!res.ok) return
      const data = await res.json()
      setNotes(data.notes || [])
    } catch (err) { console.error(err) }
  }

  const saveNote = async (type, content) => {
    try {
      const res = await authFetch(`${API}/notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename, type, content, course_id: courseId })
      })
      if (!res.ok) throw new Error('Save failed')
      const note = await res.json()
      setNotes(prev => [note, ...prev])
    } catch (err) { alert(err.message) }
  }

  const deleteNote = async (id) => {
    try {
      await authFetch(`${API}/notes/${id}`, { method: 'DELETE' })
      setNotes(prev => prev.filter(n => n.id !== id))
    } catch (err) { console.error(err) }
  }

  const handlePreview = async () => {
    if (previewing) return
    setPreviewing(true)
    setPreviewData(null)
    try {
      const res = await authFetch(`${API}/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename, course_id: courseId })
      })
      if (!res.ok) throw new Error((await res.json()).detail)
      setPreviewData(await res.json())
    } catch (err) { alert(err.message) }
    setPreviewing(false)
  }

  const handleAsk = async () => {
    if (!question.trim() || asking) return
    const q = question
    setQuestion('')
    setAsking(true)
    const newHistory = [...history, { role: 'user', content: q }]
    setHistory(newHistory)
    try {
      const res = await authFetch(`${API}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, filename, course_id: courseId, history })
      })
      const data = await res.json()
      setHistory([...newHistory, {
        role: 'assistant',
        content: data.answer,
        sources: data.sources,
        source_type: data.source_type
      }])
    } catch (err) {
      setHistory([...newHistory, { role: 'assistant', content: `Error: ${err.message}` }])
    }
    setAsking(false)
  }

  const handleStartQuiz = async () => {
    if (loadingQuiz) return
    setLoadingQuiz(true)
    setQuizQuestions([])
    setCurrentIndex(0)
    setSelectedOption(null)
    setShowResult(false)
    setScore(0)
    setQuizFinished(false)
    try {
      const res = await authFetch(`${API}/quiz`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename, course_id: courseId, num_questions: 5 })
      })
      if (!res.ok) throw new Error((await res.json()).detail)
      const data = await res.json()
      setQuizQuestions(data.questions)
    } catch (err) { alert(err.message) }
    setLoadingQuiz(false)
  }

  const handleSelectOption = (option) => {
    if (showResult) return
    setSelectedOption(option)
    setShowResult(true)
    if (option === quizQuestions[currentIndex].answer) setScore(prev => prev + 1)
  }

  const handleNextQuestion = async () => {
    if (currentIndex + 1 >= quizQuestions.length) {
      setQuizFinished(true)
      try {
        await authFetch(`${API}/quiz/result`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename, course_id: courseId, score, total: quizQuestions.length })
        })
      } catch (err) { console.error(err) }
    } else {
      setCurrentIndex(prev => prev + 1)
      setSelectedOption(null)
      setShowResult(false)
    }
  }

  const selectMode = (m) => {
    setMode(m)
    if (m === 'preview' && !previewData && !previewing) handlePreview()
  }

  const modes = [
    { id: 'preview', label: 'Preview', desc: 'Summary & vocabulary' },
    { id: 'learn', label: 'Learn', desc: 'Ask questions' },
    { id: 'quiz', label: 'Quiz', desc: 'Test your knowledge' }
  ]

  return (
    <div>
      <button style={s.backBtn} onClick={onBack}>← Back</button>
      <h1 style={{ ...s.pageTitle, marginBottom: 8 }}>{filename}</h1>

      <div style={s.notesBar}>
        <button style={s.notesToggle} onClick={() => setShowNotes(!showNotes)}>
          {showNotes ? 'Hide Notes' : `Notes (${notes.length})`}
        </button>
      </div>

      {showNotes && (
        <div style={s.notesPanel}>
          {notes.length === 0
            ? <p style={s.emptyText}>No notes saved yet.</p>
            : notes.map(note => (
              <div key={note.id} style={s.noteItem}>
                <div style={s.noteHeader}>
                  <span style={s.noteType}>{note.type}</span>
                  <span style={s.noteMeta}>{new Date(note.created_at).toLocaleDateString()}</span>
                  <button style={s.noteDelete} onClick={() => deleteNote(note.id)}>×</button>
                </div>
                <div style={s.noteContent}><AnswerRenderer text={note.content} /></div>
              </div>
            ))
          }
        </div>
      )}

      {/* Mode selector */}
      <div style={s.modeGrid}>
        {modes.map(m => (
          <div key={m.id}
            style={{ ...s.modeCard, ...(mode === m.id ? s.modeCardActive : {}) }}
            onClick={() => selectMode(m.id)}>
            <h3 style={{ ...s.modeTitle, ...(mode === m.id ? { color: 'rgba(255,255,255,0.92)' } : {}) }}>{m.label}</h3>
            <p style={{ ...s.modeDesc, ...(mode === m.id ? { color: 'rgba(255,255,255,0.38)' } : {}) }}>{m.desc}</p>
          </div>
        ))}
      </div>

      {/* Preview content */}
      {mode === 'preview' && (
        <div style={s.contentArea}>
          {previewing && <p style={s.loadingText}>Generating preview...</p>}
          {previewData && (
            <>
              <div style={s.summaryBlock}>
                <p style={s.summaryLang}>Deutsch</p>
                <p style={s.summaryText}>{previewData.summary_de}</p>
              </div>
              <div style={{ ...s.summaryBlock, background: '#f0f9ff' }}>
                <p style={s.summaryLang}>中文</p>
                <p style={s.summaryText}>{previewData.summary_zh}</p>
              </div>
              {previewData.mindmap && (
                <div style={{ marginTop: 24 }}>
                  <p style={s.contentLabel}>Lecture Structure</p>
                  <AnswerRenderer text={previewData.mindmap} />
                </div>
              )}
              <div style={{ marginTop: 24 }}>
                <p style={s.contentLabel}>Key Vocabulary</p>
                <div style={s.vocabGrid}>
                  {previewData.vocabulary.map((item, i) => (
                    <div key={i} style={s.vocabItem}>{typeof item === 'string' ? item : item}</div>
                  ))}
                </div>
              </div>
              <button style={s.saveNoteBtn} onClick={() => saveNote('summary', previewData.summary_zh)}>
                Save summary as note
              </button>
            </>
          )}
        </div>
      )}

      {/* Learn content */}
      {mode === 'learn' && (
        <div style={s.contentArea}>
          <div style={s.chatHistory}>
            {history.length === 0 && <p style={s.emptyText}>Ask anything about this document.</p>}
            {history.map((msg, i) => (
              <div key={i} style={msg.role === 'user' ? s.userBubble : s.aiBubble}>
                <p style={s.bubbleLabel}>{msg.role === 'user' ? 'You' : 'AI'}</p>
                {msg.role === 'user'
                  ? <p style={s.bubbleText}>{msg.content}</p>
                  : <AnswerRenderer text={msg.content} />
                }
                {msg.role === 'assistant' && msg.source_type === 'pdf' && msg.sources?.pages?.length > 0 && (
                  <p style={s.sourceTag}>Pages: {msg.sources.pages.join(', ')}</p>
                )}
                {msg.role === 'assistant' && msg.source_type === 'pdf+web' && (
                  <p style={{ ...s.sourceTag, color: coral, fontWeight: 600 }}>PDF + Web</p>
                )}
                {msg.role === 'assistant' && (
                  <button style={s.inlineNoteBtn} onClick={() => saveNote('answer', msg.content)}>
                    Save as note
                  </button>
                )}
              </div>
            ))}
            {asking && <p style={s.loadingText}>Thinking...</p>}
          </div>
          <div style={s.chatInputRow}>
            <input style={s.chatInput} value={question}
              onChange={e => setQuestion(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !asking && handleAsk()}
              placeholder="Ask a question about this document..."
              disabled={asking} />
            <button style={asking ? s.chatBtnDisabled : s.chatBtn} onClick={handleAsk} disabled={asking}>
              Ask
            </button>
          </div>
          {history.length > 0 && (
            <button style={s.clearBtn} onClick={() => setHistory([])}>Clear conversation</button>
          )}
        </div>
      )}

      {/* Quiz content */}
      {mode === 'quiz' && (
        <div style={s.contentArea}>
          {loadingQuiz && <p style={s.loadingText}>Generating questions...</p>}

          {!loadingQuiz && quizQuestions.length === 0 && !quizFinished && (
            <button style={s.actionBtn} onClick={handleStartQuiz}>Generate Quiz</button>
          )}

          {quizQuestions.length > 0 && !quizFinished && (
            <>
              <div style={s.quizMeta}>
                <span style={s.quizMetaText}>Question {currentIndex + 1} of {quizQuestions.length}</span>
                <span style={s.quizScoreText}>Score: {score}/{currentIndex}</span>
              </div>
              <div style={s.progressBg}>
                <div style={{ ...s.progressFill, width: `${(currentIndex / quizQuestions.length) * 100}%` }} />
              </div>
              <p style={s.quizQuestion}>{quizQuestions[currentIndex].question}</p>
              <div style={s.optionsList}>
                {Object.entries(quizQuestions[currentIndex].options).map(([key, val]) => {
                  let optStyle = s.optionBtn
                  if (showResult) {
                    if (key === quizQuestions[currentIndex].answer) optStyle = s.optionCorrect
                    else if (key === selectedOption) optStyle = s.optionWrong
                  } else if (key === selectedOption) {
                    optStyle = s.optionSelected
                  }
                  return (
                    <button key={key} style={optStyle} onClick={() => handleSelectOption(key)} disabled={showResult}>
                      <strong>{key}.</strong> {val}
                    </button>
                  )
                })}
              </div>
              {showResult && (
                <div style={s.explanation}>
                  <strong>
                    {selectedOption === quizQuestions[currentIndex].answer
                      ? 'Correct!'
                      : `Wrong — correct answer: ${quizQuestions[currentIndex].answer}`}
                  </strong>
                  <p style={{ marginTop: 8, fontSize: 14 }}>{quizQuestions[currentIndex].explanation}</p>
                </div>
              )}
              {showResult && (
                <button style={{ ...s.actionBtn, marginTop: 20 }} onClick={handleNextQuestion}>
                  {currentIndex + 1 >= quizQuestions.length ? 'View Results' : 'Next →'}
                </button>
              )}
            </>
          )}

          {quizFinished && (
            <div style={s.scoreCard}>
              <div style={s.scoreBig}>{score}<span style={s.scoreTotal}>/{quizQuestions.length}</span></div>
              <p style={s.scorePct}>{Math.round((score / quizQuestions.length) * 100)}% mastery</p>
              <div style={s.progressBg}>
                <div style={{
                  ...s.progressFill,
                  width: `${(score / quizQuestions.length) * 100}%`,
                  background: score / quizQuestions.length >= 0.8 ? sage : coral
                }} />
              </div>
              <button style={{ ...s.actionBtn, marginTop: 32 }} onClick={handleStartQuiz}>Try Again</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Root App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [token, setToken] = useState(getToken())
  const [user, setUser] = useState(getUserData())
  const [view, setView] = useState('courses')
  const [selectedCourse, setSelectedCourse] = useState(null)
  const [selectedPdf, setSelectedPdf] = useState(null)
  const [sidebarRefresh, setSidebarRefresh] = useState(0)

  const handleLogin = (userData) => {
    setToken(getToken())
    saveUserData(userData)
    setUser(userData)
  }

  const handleLogout = () => {
    removeToken()
    removeUserData()
    window.location.reload()
  }

  const handleSelectCourse = (course) => {
    setSelectedCourse(course)
    setView('course')
  }

  const handleSelectPdf = (course, filename) => {
    setSelectedCourse(course)
    setSelectedPdf(filename)
    setView('learn')
  }

  const handleUploadDone = () => {
    setSidebarRefresh(prev => prev + 1)
  }

  if (!token) return <><GlobalStyle /><AuthScreen onLogin={handleLogin} /></>

  return (
    <div style={s.appLayout}>
      <GlobalStyle />
      <Sidebar
        user={user}
        selectedCourse={selectedCourse}
        selectedPdf={selectedPdf}
        onSelectCourse={handleSelectCourse}
        onSelectPdf={handleSelectPdf}
        onGoHome={() => { setView('courses'); setSelectedCourse(null); setSelectedPdf(null) }}
        onLogout={handleLogout}
        refreshKey={sidebarRefresh}
      />
      <main style={s.mainContent}>
        {view === 'courses' && (
          <CoursesView onSelectCourse={handleSelectCourse} />
        )}
        {view === 'course' && selectedCourse && (
          <CourseDetailView
            course={selectedCourse}
            onSelectPdf={f => handleSelectPdf(selectedCourse, f)}
            onBack={() => { setView('courses'); setSelectedCourse(null) }}
            onUploadDone={handleUploadDone}
          />
        )}
        {view === 'learn' && selectedPdf && (
          <LearnView
            filename={selectedPdf}
            courseId={selectedCourse?.id}
            onBack={() => setView('course')}
          />
        )}
      </main>
    </div>
  )
}

// ─── Styles ───────────────────────────────────────────────────────────────────
const glass = {
  background: '#FFFFFF',
  border: '2px solid #111111',
}
const glassSubtle = {
  background: '#FFFFFF',
  border: '2px solid #111111',
}
const ff = '"DM Sans", system-ui, sans-serif'

// ── Colour tokens ──────────────────────────────────────────────────────────────
const indigo  = '#2D2AFF'   // primary — sidebar, buttons, active states
const coral   = '#FF5C3A'   // secondary — alerts, pdf+web tag, wrong answers
const sage    = '#7EC8A4'   // tertiary — correct answers, progress
const yellow  = '#FFD166'   // highlight — active sidebar item, score accent
const accent  = indigo

const ink   = '#111111'
const muted = 'rgba(0,0,0,0.52)'
const faint = 'rgba(0,0,0,0.32)'

// Course card background palette (cycles by index)
const cardPalette = ['#EDE9FF', '#FFE8E3', '#E3F5EC', '#FFF6DE']
const cardBorderPalette = ['#C4BFFF', '#FFBFB0', '#A8E4C4', '#FFE5A0']

const s = {
  appLayout: { display: 'flex', minHeight: '100vh', fontFamily: ff },
  mainContent: { marginLeft: 240, flex: 1, padding: '52px 72px', maxWidth: 1020, boxSizing: 'border-box' },

  // Sidebar — solid indigo
  sidebar: { width: 240, height: '100vh', background: indigo, borderRight: 'none', position: 'fixed', left: 0, top: 0, display: 'flex', flexDirection: 'column', zIndex: 100, boxSizing: 'border-box', overflowY: 'auto' },
  sidebarLogo: { padding: '26px 22px 18px', fontSize: 18, fontWeight: 700, color: '#FFFFFF', letterSpacing: '-0.3px', borderBottom: '1px solid rgba(255,255,255,0.15)', cursor: 'pointer', flexShrink: 0 },
  sidebarNav: { flex: 1, padding: '14px 0 8px', overflowY: 'auto' },
  sidebarSection: { fontSize: 10, fontWeight: 600, color: 'rgba(255,255,255,0.45)', letterSpacing: 1.6, padding: '8px 20px 5px', margin: 0, textTransform: 'uppercase' },
  sidebarCourseRow: { display: 'flex', alignItems: 'center', gap: 7, padding: '8px 20px', cursor: 'pointer', transition: 'background 0.15s', borderRadius: 0 },
  sidebarCourseRowActive: { background: 'rgba(255,255,255,0.15)' },
  sidebarChevron: { fontSize: 9, color: 'rgba(255,255,255,0.5)', width: 11, flexShrink: 0 },
  sidebarCourseName: { fontSize: 13, color: '#FFFFFF', fontWeight: 500, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  sidebarPdfCount: { fontSize: 11, color: 'rgba(255,255,255,0.45)', flexShrink: 0 },
  sidebarPdfItem: { display: 'flex', alignItems: 'center', gap: 7, padding: '5px 12px 5px 34px', cursor: 'pointer', transition: 'all 0.15s', borderRadius: 8, margin: '1px 8px' },
  sidebarPdfItemActive: { background: yellow },
  sidebarPdfDot: { fontSize: 12, color: 'rgba(255,255,255,0.4)', flexShrink: 0, lineHeight: 1 },
  sidebarPdfName: { fontSize: 12, color: 'rgba(255,255,255,0.75)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  sidebarPdfLoading: { fontSize: 11, color: 'rgba(255,255,255,0.4)', padding: '4px 20px 4px 34px', margin: 0 },
  sidebarFooter: { padding: '14px 18px', borderTop: '1px solid rgba(255,255,255,0.15)', flexShrink: 0 },
  sidebarUserRow: { display: 'flex', alignItems: 'center', gap: 7, marginBottom: 10 },
  sidebarUserIcon: { fontSize: 13, color: 'rgba(255,255,255,0.6)' },
  sidebarUserName: { fontSize: 12, color: 'rgba(255,255,255,0.7)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 },
  sidebarLogout: { display: 'flex', alignItems: 'center', gap: 7, width: '100%', padding: '9px 12px', fontSize: 13, fontWeight: 500, color: 'rgba(255,255,255,0.85)', background: 'rgba(255,255,255,0.12)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: 10, cursor: 'pointer', transition: 'all 0.15s' },
  sidebarLogoutIcon: { fontSize: 13 },

  // Auth
  authBg: { minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' },
  authCard: { ...glass, borderRadius: 22, padding: '48px 40px', width: 400, boxShadow: '0 8px 40px rgba(45,42,255,0.12)' },
  authLogo: { fontSize: 24, fontWeight: 700, color: indigo, marginBottom: 6, letterSpacing: '-0.3px' },
  authSubtitle: { fontSize: 14, color: muted, marginBottom: 30, marginTop: 0 },
  authInput: { width: '100%', padding: '12px 16px', fontSize: 14, border: '2px solid rgba(0,0,0,0.12)', borderRadius: 10, marginBottom: 10, boxSizing: 'border-box', outline: 'none', background: '#FAFAFA', color: ink, fontFamily: ff },
  authBtn: { width: '100%', padding: '13px', fontSize: 14, fontWeight: 600, background: indigo, color: '#fff', border: 'none', borderRadius: 10, cursor: 'pointer', marginTop: 4, fontFamily: ff },
  authBtnDisabled: { width: '100%', padding: '13px', fontSize: 14, background: 'rgba(45,42,255,0.3)', color: '#fff', border: 'none', borderRadius: 10, cursor: 'not-allowed', fontFamily: ff, marginTop: 4 },
  authError: { fontSize: 13, color: coral, marginBottom: 10, marginTop: -4 },
  authToggle: { textAlign: 'center', fontSize: 13, color: muted, marginTop: 20 },
  authToggleLink: { color: indigo, cursor: 'pointer', textDecoration: 'none', fontWeight: 500 },

  // Page
  pageHeader: { display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 36 },
  pageTitle: { fontSize: 22, fontWeight: 600, color: ink, margin: '0 0 28px', letterSpacing: '-0.2px' },
  backBtn: { fontSize: 13, color: muted, background: 'transparent', border: 'none', cursor: 'pointer', padding: '0 0 20px', display: 'block' },
  sectionTitle: { fontSize: 11, fontWeight: 600, color: faint, marginBottom: 14, marginTop: 30, textTransform: 'uppercase', letterSpacing: 1.2 },
  loadingText: { color: muted, fontSize: 13 },
  emptyState: { padding: '90px 0', textAlign: 'center' },
  emptyText: { color: faint, fontSize: 14 },

  actionBtn: { padding: '9px 20px', fontSize: 13, fontWeight: 600, background: indigo, color: '#fff', border: 'none', borderRadius: 9, cursor: 'pointer' },
  textBtn: { padding: '4px 0', fontSize: 13, fontWeight: 500, color: indigo, background: 'transparent', border: 'none', cursor: 'pointer' },
  cancelBtn: { padding: '9px 16px', fontSize: 13, background: 'transparent', color: muted, border: 'none', cursor: 'pointer' },
  createForm: { display: 'flex', gap: 8, marginBottom: 32, alignItems: 'center' },
  createInput: { padding: '10px 14px', fontSize: 14, border: '2px solid rgba(0,0,0,0.12)', borderRadius: 9, flex: 1, outline: 'none', background: '#FFFFFF', fontFamily: ff },

  courseGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 16 },
  courseCard: { borderRadius: 18, padding: '26px 24px', cursor: 'pointer', position: 'relative', transition: 'all 0.2s ease', boxShadow: '0 2px 0px rgba(0,0,0,0.85)', minHeight: 136, border: '2px solid #111111' },
  courseCardHover: { transform: 'translateY(-4px) rotate(1deg)', boxShadow: '0 8px 0px rgba(0,0,0,0.85)' },
  courseCardTitle: { fontSize: 16, fontWeight: 600, color: ink, margin: '0 0 7px', letterSpacing: '-0.2px' },
  courseCardMeta: { fontSize: 12, color: muted, margin: 0 },
  cardDeleteBtn: { position: 'absolute', top: 12, right: 14, width: 24, height: 24, border: 'none', background: 'transparent', color: 'rgba(0,0,0,0.35)', fontSize: 20, cursor: 'pointer', lineHeight: 1, padding: 0 },

  uploadZone: { background: '#FFFFFF', border: `2px dashed rgba(0,0,0,0.2)`, borderRadius: 18, padding: '56px 36px', textAlign: 'center', cursor: 'pointer', marginBottom: 10, transition: 'all 0.2s ease' },
  uploadZoneDrag: { background: '#EDE9FF', border: `2px dashed ${indigo}` },
  uploadIcon: { fontSize: 28, color: indigo, marginBottom: 12 },
  uploadLabel: { fontSize: 14, color: muted, margin: 0 },
  uploadStatusText: { fontSize: 13, color: indigo, marginTop: 8, fontWeight: 500 },

  progressBg: { background: 'rgba(0,0,0,0.08)', borderRadius: 99, height: 5, overflow: 'hidden', marginBottom: 28 },
  progressFill: { background: indigo, height: 5, borderRadius: 99, transition: 'width 0.3s ease' },

  pdfList: { display: 'flex', flexDirection: 'column', gap: 8 },
  pdfItem: { ...glass, display: 'flex', alignItems: 'center', gap: 14, borderRadius: 13, padding: '13px 18px', cursor: 'pointer', transition: 'all 0.18s', boxShadow: '2px 2px 0px #111111' },
  pdfIcon: { width: 38, height: 38, background: '#EDE9FF', borderRadius: 9, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700, color: indigo, flexShrink: 0, cursor: 'pointer' },
  pdfInfo: { flex: 1, minWidth: 0, cursor: 'pointer' },
  pdfName: { fontSize: 13, fontWeight: 500, color: ink, margin: '0 0 2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  pdfMeta: { fontSize: 11, color: muted, margin: 0 },
  pdfArrow: { fontSize: 15, color: faint, cursor: 'pointer' },
  pdfDeleteBtn: { background: 'transparent', border: 'none', color: faint, fontSize: 20, cursor: 'pointer', padding: '0 4px', lineHeight: 1, flexShrink: 0 },

  notesBar: { marginBottom: 20 },
  notesToggle: { fontSize: 13, color: muted, background: 'transparent', border: 'none', cursor: 'pointer', padding: '2px 0' },
  notesPanel: { ...glass, borderRadius: 14, padding: '20px 24px', marginBottom: 24, boxShadow: '0 2px 14px rgba(0,0,0,0.06)' },
  noteItem: { padding: '12px 0', borderBottom: `1px solid rgba(0,0,0,0.07)` },
  noteHeader: { display: 'flex', alignItems: 'center', gap: 7, marginBottom: 6 },
  noteType: { fontSize: 10, fontWeight: 600, background: `rgba(0,0,0,0.07)`, color: accent, padding: '2px 8px', borderRadius: 4, textTransform: 'uppercase', letterSpacing: 0.5 },
  noteMeta: { fontSize: 11, color: faint },
  noteDelete: { marginLeft: 'auto', background: 'transparent', border: 'none', cursor: 'pointer', fontSize: 18, color: faint, lineHeight: 1 },
  noteContent: { fontSize: 13, color: ink },

  modeGrid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 24 },
  modeCard: { background: '#FFFFFF', border: '2px solid #111111', borderRadius: 14, padding: '18px 20px', cursor: 'pointer', transition: 'all 0.2s ease', boxShadow: '2px 2px 0px #111111' },
  modeCardActive: { background: indigo, border: `2px solid ${indigo}`, boxShadow: `3px 3px 0px rgba(0,0,0,0.5)` },
  modeTitle: { fontSize: 15, fontWeight: 600, margin: '0 0 3px', color: ink },
  modeDesc: { fontSize: 12, color: muted, margin: 0 },

  contentArea: { background: '#FFFFFF', border: '2px solid #111111', borderRadius: 18, padding: '32px 36px', boxShadow: '4px 4px 0px #111111' },
  summaryBlock: { background: '#FAF7F2', borderRadius: 12, padding: '20px 24px', marginBottom: 14, border: `1px solid rgba(0,0,0,0.08)` },
  summaryLang: { fontSize: 10, fontWeight: 700, color: indigo, letterSpacing: 1.4, marginBottom: 8, marginTop: 0, textTransform: 'uppercase' },
  summaryText: { fontSize: 14, lineHeight: 1.85, color: ink, margin: 0 },
  contentLabel: { fontSize: 10, fontWeight: 600, color: faint, letterSpacing: 1.2, marginBottom: 12, marginTop: 0, textTransform: 'uppercase' },
  vocabGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(165px, 1fr))', gap: 8 },
  vocabItem: { background: '#EDE9FF', border: '1.5px solid #C4BFFF', borderRadius: 9, padding: '8px 12px', fontSize: 13, color: ink },
  saveNoteBtn: { marginTop: 24, padding: '7px 14px', fontSize: 12, background: 'transparent', border: 'none', cursor: 'pointer', color: muted },

  chatHistory: { minHeight: 180, marginBottom: 24 },
  userBubble: { background: '#EDE9FF', borderRadius: 12, padding: '12px 16px', marginBottom: 14, border: `1.5px solid #C4BFFF` },
  aiBubble: { padding: '12px 0', marginBottom: 14, borderBottom: `1px solid rgba(0,0,0,0.07)` },
  bubbleLabel: { fontSize: 10, fontWeight: 700, color: indigo, marginBottom: 6, marginTop: 0, textTransform: 'uppercase', letterSpacing: 0.8 },
  bubbleText: { fontSize: 14, color: ink, margin: 0, lineHeight: 1.72 },
  sourceTag: { fontSize: 11, color: indigo, marginTop: 5, marginBottom: 0, fontWeight: 500 },
  inlineNoteBtn: { marginTop: 8, padding: '3px 10px', fontSize: 11, background: 'transparent', border: 'none', cursor: 'pointer', color: faint },
  chatInputRow: { display: 'flex', gap: 8 },
  chatInput: { flex: 1, padding: '12px 16px', fontSize: 14, border: '2px solid #111111', borderRadius: 11, outline: 'none', background: '#FFFFFF', color: ink, fontFamily: ff },
  chatBtn: { padding: '12px 20px', fontSize: 13, fontWeight: 600, background: indigo, color: '#fff', border: 'none', borderRadius: 11, cursor: 'pointer' },
  chatBtnDisabled: { padding: '12px 20px', fontSize: 13, background: 'rgba(45,42,255,0.3)', color: '#fff', border: 'none', borderRadius: 11, cursor: 'not-allowed' },
  clearBtn: { marginTop: 12, fontSize: 12, color: faint, background: 'transparent', border: 'none', cursor: 'pointer' },

  quizMeta: { display: 'flex', justifyContent: 'space-between', marginBottom: 8 },
  quizMetaText: { fontSize: 13, color: muted },
  quizScoreText: { fontSize: 13, color: indigo, fontWeight: 600 },
  quizQuestion: { fontSize: 17, fontWeight: 600, lineHeight: 1.6, color: ink, marginBottom: 20, marginTop: 0 },
  optionsList: { display: 'flex', flexDirection: 'column', gap: 8 },
  optionBtn: { padding: '13px 18px', fontSize: 14, textAlign: 'left', background: '#FFFFFF', border: '2px solid #111111', borderRadius: 11, cursor: 'pointer', color: ink, transition: 'all 0.15s', fontFamily: ff, boxShadow: '2px 2px 0px #111111' },
  optionSelected: { padding: '13px 18px', fontSize: 14, textAlign: 'left', background: '#EDE9FF', border: `2px solid ${indigo}`, borderRadius: 11, cursor: 'pointer', color: indigo, fontFamily: ff, fontWeight: 500 },
  optionCorrect: { padding: '13px 18px', fontSize: 14, textAlign: 'left', background: '#E3F5EC', border: `2px solid ${sage}`, borderRadius: 11, color: '#1a7a4a', cursor: 'default', fontFamily: ff, fontWeight: 500 },
  optionWrong: { padding: '13px 18px', fontSize: 14, textAlign: 'left', background: '#FFE8E3', border: `2px solid ${coral}`, borderRadius: 11, color: coral, cursor: 'default', fontFamily: ff },
  explanation: { background: '#FFF6DE', border: `1.5px solid #FFE5A0`, borderRadius: 11, padding: '15px 20px', marginTop: 18, fontSize: 13, lineHeight: 1.72 },

  scoreCard: { textAlign: 'center', padding: '44px 0' },
  scoreBig: { fontSize: 72, fontWeight: 700, color: indigo, lineHeight: 1 },
  scoreTotal: { fontSize: 36, color: faint },
  scorePct: { fontSize: 15, color: muted, margin: '12px 0 24px' },
}
