import { useState, useEffect } from 'react'
import AnswerRenderer from './AnswerRenderer'

const API = 'http://localhost:8000'  // 对接后端API地址

function App() {
  // upload相关状态
  const [uploadStatus, setUploadStatus] = useState('')
  const [filename, setFilename] = useState('')
  // ask相关状态
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [sources, setSources] = useState([])      // 页码来源
  const [history, setHistory] = useState([])      // 对话历史
  const [uploading, setUploading] = useState(false)
  const [asking, setAsking] = useState(false)
  // preview相关状态
  const [previewData, setPreviewData] = useState(null)   // 存储preview返回的数据
  const [previewing, setPreviewing] = useState(false)     // 是否正在加载
  // quiz相关状态
  const [quizQuestions, setQuizQuestions] = useState([])     // 所有题目
  const [currentIndex, setCurrentIndex] = useState(0)        // 当前第几题（从0开始）
  const [selectedOption, setSelectedOption] = useState(null)  // 用户选择了哪个选项
  const [showResult, setShowResult] = useState(false)         // 是否显示对错结果
  const [score, setScore] = useState(0)                       // 答对的题数
  const [quizFinished, setQuizFinished] = useState(false)     // 是否做完所有题
  const [loadingQuiz, setLoadingQuiz] = useState(false)       // 是否正在加载题目
  // note相关状态
  const [notes, setNotes] = useState([])
  const [showNotes, setShowNotes] = useState(false)

  // course相关状态
  const [courses, setCourses] = useState([])
  const [selectedCourseId, setSelectedCourseId] = useState(1)
  const [coursesLoading, setCoursesLoading] = useState(false)

  useEffect(() => {
    loadCourses()
  }, [])

  // load, create, delete course
  const loadCourses = async () => {
    setCoursesLoading(true)
    try {
      const res = await fetch(`${API}/courses`)
      const data = await res.json()
      setCourses(data.courses || [])
    } catch (err) {
      console.error('Failed to load courses:', err)
    }
    setCoursesLoading(false)
  }

  const createCourse = async () => {
    const title = prompt('Course name:')
    if (!title || !title.trim()) return

    try {
      const res = await fetch(`${API}/courses`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title.trim() })
      })
      if (!res.ok) throw new Error('Create failed')
      await loadCourses()
    } catch (err) {
      alert(`Create course failed: ${err.message}`)
    }
  }

  const deleteCourse = async (courseId) => {
    if (courseId === 1) {
      alert('Default course cannot be deleted')
      return
    }
    if (!confirm('Delete this course and all its PDFs?')) return

    try {
      const res = await fetch(`${API}/courses/${courseId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('Delete failed')
      await loadCourses()

      // 如果删的是当前选中的课程，切回默认课程
      if (selectedCourseId === courseId) {
        setSelectedCourseId(1)
      }
    } catch (err) {
      alert(`Delete course failed: ${err.message}`)
    }
  }

  // 处理PDF上传Upload
  const handleUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return

    setUploading(true)
    setUploadStatus('Uploading...')

    const formData = new FormData()
    formData.append('file', file)
    formData.append('course_id', selectedCourseId)   // ← 新增这行

    try {
      const res = await fetch(`${API}/upload`, {
        method: 'POST',
        body: formData
      })
      const data = await res.json()
      setFilename(data.filename)
      setUploadStatus('Processing PDF...')
      setHistory([])
      pollUploadStatus(data.filename)

    } catch (err) {
      setUploadStatus(`Upload failed: ${err.message}`)
      setUploading(false)
    }
  }

  const pollUploadStatus = (filename) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API}/upload/status/${encodeURIComponent(filename)}`)
        const data = await res.json()

        if (data.status === 'done') {
          clearInterval(interval)
          setUploadStatus(`✅ ${filename} ready — ${data.chunks} chunks`)
          setUploading(false)

          // 加载该 PDF 的历史对话
          await loadMessages(filename)
          await loadNotes(filename)

        } else if (data.status === 'error') {
          clearInterval(interval)
          setUploadStatus(`Processing failed: ${data.message}`)
          setUploading(false)
        } else {
          setUploadStatus(`Processing PDF... ${data.progress}%`)
        }
      } catch (err) {
        clearInterval(interval)
        setUploadStatus(`Error checking status: ${err.message}`)
        setUploading(false)
      }
    }, 2000)
  }

  // Note operations: load, save and delete
  const loadNotes = async (filename) => {
    try {
      const res = await fetch(`${API}/notes/${encodeURIComponent(filename)}?course_id=${selectedCourseId}`)
      if (!res.ok) return
      const data = await res.json()
      setNotes(data.notes || [])
    } catch (err) {
      console.error('Failed to load notes:', err)
    }
  }

  const saveNote = async (type, content) => {
    try {
      const res = await fetch(`${API}/notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: filename,
          type: type,
          content: content,
          course_id: selectedCourseId
        })
      })
      if (!res.ok) throw new Error('Save failed')
      const newNote = await res.json()
      setNotes(prev => [newNote, ...prev])
    } catch (err) {
      alert(`Save note failed: ${err.message}`)
    }
  }

  const deleteNote = async (noteId) => {
    try {
      await fetch(`${API}/notes/${noteId}`, { method: 'DELETE' })
      setNotes(prev => prev.filter(n => n.id !== noteId))
    } catch (err) {
      console.error('Failed to delete note:', err)
    }
  }

  // 加载历史消息 messages接口
  const loadMessages = async (filename) => {
    try {
      const res = await fetch(`${API}/messages/${encodeURIComponent(filename)}?course_id=${selectedCourseId}`)
      if (!res.ok) return

      const data = await res.json()
      if (data.messages && data.messages.length > 0) {
        setHistory(data.messages)
        console.log(`Loaded ${data.messages.length} historical messages`)
      }
    } catch (err) {
      console.error('Failed to load messages:', err)
    }
  }

  // 处理提问Ask
  const handleAsk = async () => {
    if (!question.trim() || !filename || asking) return

    const currentQuestion = question
    setQuestion('')
    setAsking(true)
    setAnswer('')
    setSources([])

    const newHistory = [...history, { role: 'user', content: currentQuestion }]

    try {
      const response = await fetch(`${API}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          history: history,
          question: currentQuestion,
          filename: filename,
          course_id: selectedCourseId
        })
      })

      const data = await response.json()

      setAnswer(data.answer)
      setSources(data.sources)

      setHistory([
        ...newHistory,
        { role: 'assistant', content: data.answer, sources: data.sources }
      ])

    } catch (err) {
      setAnswer(`Error: ${err.message}`)
    }

    setAsking(false)
  }


  // 处理Preview生成
  const handlePreview = async () => {
    if (!filename || previewing) return

    setPreviewing(true)
    setPreviewData(null)

    try {
      const response = await fetch(`${API}/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: filename, course_id: selectedCourseId })
      })
      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || 'Failed to generate preview')
      }

      const data = await response.json()
      setPreviewData(data)
    } catch (err) {
      alert(`Preview Error: ${err.message}`)
    }
    setPreviewing(false)
  }

  //处理回车键提问
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !asking) {
      handleAsk()
    }
  }

  // 清空对话
  const handleClear = () => {
    setHistory([])
    setAnswer('')
    setSources([])
  }

  // 生成Quiz题目
  const handleStartQuiz = async () => {
    if (!filename || loadingQuiz || uploading) return

    setLoadingQuiz(true)
    setQuizQuestions([])
    setCurrentIndex(0)
    setSelectedOption(null)
    setShowResult(false)
    setScore(0)
    setQuizFinished(false)

    try {
      const response = await fetch(`${API}/quiz`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: filename, course_id: selectedCourseId, num_questions: 5 })
      })
      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || 'Failed to generate quiz')
      }

      const data = await response.json()
      setQuizQuestions(data.questions)
    } catch (err) {
      alert(`Quiz Error: ${err.message}`)
    }

    setLoadingQuiz(false)
  }

  const handleSelectOption = (option) => {
    if (showResult) return //如果已经显示结果了，就不允许再选了

    setSelectedOption(option)
    setShowResult(true)

    const currentQuestion = quizQuestions[currentIndex]
    if (option === currentQuestion.answer) {
      setScore(prev => prev + 1)
    }
  }

  const handleNextQuestion = async () => {
    if (currentIndex + 1 >= quizQuestions.length) {
      setQuizFinished(true)

      // save to database
      try {
        await fetch(`${API}/quiz/result`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            filename: filename,
            course_id: selectedCourseId,
            score: score,
            total: quizQuestions.length
          })
        })
      } catch (err) {
        console.error('Failed to save quiz result:', err)
      }

      // save to localStorage
      const progressKey = `quiz_progress_${filename}`
      const progressData = {
        filename: filename,
        score: score,
        total: quizQuestions.length,
        date: new Date().toLocaleDateString()
      }
      localStorage.setItem(progressKey, JSON.stringify(progressData))
    } else {
      setCurrentIndex(prev => prev + 1)
      setSelectedOption(null)
      setShowResult(false)
    }
  }

  const handleRestartQuiz = () => {
    setCurrentIndex(0)
    setSelectedOption(null)
    setShowResult(false)
    setScore(0)
    setQuizFinished(false)
    setQuizQuestions([])
  }




  // HTML
  return (
    <div style={styles.container}>
      <h1 style={styles.title}>EduPrep</h1>

      {/* 课程选择栏 */}
      <div style={styles.courseBar}>
        <span style={{ fontSize: 14, color: '#374151', marginRight: 8 }}>Course:</span>
        <select
          value={selectedCourseId}
          onChange={(e) => setSelectedCourseId(Number(e.target.value))}
          style={styles.courseSelect}
        >
          {courses.map(c => (
            <option key={c.id} value={c.id}>
              {c.title} ({c.pdf_count} PDFs)
            </option>
          ))}
        </select>
        <button onClick={createCourse} style={styles.btnSmall}>+ New</button>
        {selectedCourseId !== 1 && (
          <button onClick={() => deleteCourse(selectedCourseId)} style={styles.btnSmallDanger}>
            Delete
          </button>
        )}
      </div>

      <button
        onClick={() => setShowNotes(prev => !prev)}
        style={styles.btn}
        disabled={!filename}
      >
        {showNotes ? 'Hide Notes' : `Notes (${notes.length})`}
      </button>

      {showNotes && (
        <div style={styles.card}>
          <h2 style={styles.cardTitle}>Notes</h2>
          {notes.length === 0 ? (
            <p style={{ color: '#9ca3af', fontSize: 13 }}>No notes saved yet.</p>
          ) : (
            notes.map(note => (
              <div key={note.id} style={styles.noteItem}>
                <div style={styles.noteHeader}>
                  <span style={styles.noteType}>{note.type}</span>
                  <span style={styles.noteDate}>
                    {new Date(note.created_at).toLocaleDateString()}
                  </span>
                  <button
                    onClick={() => deleteNote(note.id)}
                    style={styles.deleteNoteBtn}
                  >
                    🗑️
                  </button>
                </div>
                <div style={styles.noteContent}>
                  <AnswerRenderer text={note.content} />
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* 上传区域 */}
      <div style={styles.card}>
        <h2 style={styles.cardTitle}>Upload PDF</h2>
        <input type="file" accept=".pdf" onChange={handleUpload} disabled={uploading} />
        {uploadStatus && <p style={styles.status}>{uploadStatus}</p>}
      </div>

      {/* Preview 触发按钮 */}
      <div style={styles.card}>
        <h2 style={styles.cardTitle}>Preview Mode</h2>
        <p style={{ fontSize: 14, color: '#666', marginBottom: 12, marginTop: 0 }}>
          Automatically generate lecture notes summary and key vocabulary list
        </p>
        <button
          onClick={handlePreview}
          disabled={!filename || previewing || uploading}
          style={!filename || previewing || uploading ? styles.btnDisabled : styles.btn}
        >
          {previewing ? 'Generating, please wait...' : 'Generate Preview'}
        </button>
      </div>

      {/* Preview 结果 */}
      {previewData && (
        <div style={styles.card}>

          {/* 双语摘要 */}
          <h2 style={styles.cardTitle}>Summary</h2>

          <div style={styles.summaryBox}>
            <p style={styles.summaryLabel}>🇩🇪 Deutsch</p>
            <p style={styles.summaryText}>{previewData.summary_de}</p>
          </div>

          <div style={{ ...styles.summaryBox, background: '#f0f9ff' }}>
            <p style={styles.summaryLabel}>🇨🇳 中文</p>
            <p style={styles.summaryText}>{previewData.summary_zh}</p>
          </div>

          {/* 词汇列表 */}
          <h2 style={{ ...styles.cardTitle, marginTop: 24 }}>Key Words</h2>

          {/* Mindmap */}
          {previewData.mindmap && (
            <div style={styles.card}>
              <h2 style={styles.cardTitle}>Lecture Structure</h2>
              <AnswerRenderer text={previewData.mindmap} />
            </div>
          )}

          <div style={styles.vocabList}>
            {previewData.vocabulary.map((item, index) => (
              <div key={index} style={styles.vocabCard}>
                {typeof item === 'string' ? item : item.term}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 对话历史 */}
      {history.length > 0 && (
        <div style={styles.card}>
          <div style={styles.historyHeader}>
            <h2 style={styles.cardTitle}>Dialogue</h2>
            <button onClick={handleClear} style={styles.clearBtn}>Clear</button>
          </div>
          {history.map((msg, i) => (
            <div key={i} style={msg.role === 'user' ? styles.userMsg : styles.aiMsg}>
              <strong>{msg.role === 'user' ? 'You' : 'AI'}：</strong>
              {msg.role === 'user'
                ? msg.content
                : <AnswerRenderer text={msg.content} />
              }
              {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                <div style={{ fontSize: 12, color: '#2563eb', marginTop: 4 }}>
                  Sources from Page： {msg.sources.join('、')}
                </div>
              )}
              {/* 保存笔记按钮 */}
              {msg.role === 'assistant' && (
                <button
                  onClick={() => saveNote('answer', msg.content)}
                  style={styles.saveNoteBtn}
                >
                  Save as Note
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 当前回答 */}
      {(answer || asking) && (
        <div style={styles.card}>
          <h2 style={styles.cardTitle}>
            AI Answer
            {asking && <span style={{ color: '#9ca3af' }}> Thinking...</span>}
          </h2>
          {sources.length > 0 && (
            <p style={styles.sources}>
              Sources from Page： {sources.join('、')}
            </p>
          )}
          <AnswerRenderer text={answer} />
        </div>
      )}

      {msg.source_type === 'pdf' && msg.sources?.length > 0 && (
        <div style={{ fontSize: 12, color: '#2563eb', marginTop: 4 }}>
          Sources from Page：{msg.sources.join('、')}
        </div>
      )}
      {msg.source_type === 'pdf+web' && (
        <div style={{ fontSize: 12, color: '#7c3aed', marginTop: 4 }}>
          PDF + Web
        </div>
      )}
      {msg.source_type === 'web' && (
        <div style={{ fontSize: 12, color: '#059669', marginTop: 4 }}>
          Web Search
        </div>
      )}

      {/* 输入框 */}
      <div style={styles.card}>
        <h2 style={styles.cardTitle}>Ask a Question</h2>
        <input
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={filename ? 'Enter your question, then press Enter...' : 'Please upload a PDF first'}
          disabled={asking || !filename || uploading}
          placeholder={uploading ? 'Please wait, processing PDF...' : filename ? 'Enter your question...' : 'Please upload a PDF first'}
          style={styles.input}
        />
        <button
          onClick={handleAsk}
          disabled={asking || !filename || uploading}
          style={asking || !filename || uploading ? styles.btnDisabled : styles.btn}
        >
          {asking ? 'Answering...' : 'Ask'}
        </button>
      </div>
      {/* Review 模式 */}
      <div style={styles.card}>
        <h2 style={styles.cardTitle}>Review Mode</h2>
        <p style={{ fontSize: 14, color: '#666', marginBottom: 12, marginTop: 0 }}>
          Generate a quiz based on the lecture content
        </p>
        <button
          onClick={handleStartQuiz}
          disabled={!filename || loadingQuiz || uploading}
          style={!filename || loadingQuiz || uploading ? styles.btnDisabled : styles.btn}
        >
          {loadingQuiz ? 'Generating questions...' : 'Start Quiz'}
        </button>
      </div>

      {/* Quiz 答题区域 */}
      {
        quizQuestions.length > 0 && !quizFinished && (
          <div style={styles.card}>

            {/* 进度显示 */}
            <div style={styles.quizProgress}>
              <span style={styles.quizProgressText}>
                Question {currentIndex + 1} of {quizQuestions.length}
              </span>
              <span style={styles.quizScore}>
                Current Score: {score} / {currentIndex}
              </span>
            </div>

            {/* 进度条 */}
            <div style={styles.progressBarBg}>
              <div style={{
                ...styles.progressBarFill,
                width: `${(currentIndex / quizQuestions.length) * 100}%`
              }} />
            </div>

            {/* 题目 */}
            <p style={styles.quizQuestion}>
              {quizQuestions[currentIndex].question}
            </p>

            {/* 选项 */}
            <div style={styles.optionsList}>
              {Object.entries(quizQuestions[currentIndex].options).map(([key, value]) => {

                // 根据答题状态决定每个选项的颜色
                let optionStyle = styles.optionBtn
                if (showResult) {
                  if (key === quizQuestions[currentIndex].answer) {
                    optionStyle = styles.optionCorrect   // 正确答案显示绿色
                  } else if (key === selectedOption) {
                    optionStyle = styles.optionWrong     // 选错了显示红色
                  }
                } else if (key === selectedOption) {
                  optionStyle = styles.optionSelected      // 选中但还没判断
                }

                return (
                  <button
                    key={key}
                    onClick={() => handleSelectOption(key)}
                    disabled={showResult}
                    style={optionStyle}
                  >
                    <strong>{key}.</strong> {value}
                  </button>
                )
              })}
            </div>

            {/* 解析（选完才显示） */}
            {showResult && (
              <div style={styles.explanation}>
                <strong>
                  {selectedOption === quizQuestions[currentIndex].answer
                    ? 'Answer is correct!'
                    : `Answer is wrong, the correct answer is ${quizQuestions[currentIndex].answer}`
                  }
                </strong>
                <p style={{ margin: '8px 0 0 0', fontSize: 14 }}>
                  {quizQuestions[currentIndex].explanation}
                </p>
              </div>
            )}

            {/* 下一题按钮 */}
            {showResult && (
              <button onClick={handleNextQuestion} style={{ ...styles.btn, marginTop: 16 }}>
                {currentIndex + 1 >= quizQuestions.length ? 'View Results' : 'Next Question →'}
              </button>
            )}
          </div>
        )
      }

      {/* Quiz 完成结果页 */}
      {
        quizFinished && (
          <div style={styles.card}>
            <h2 style={styles.cardTitle}>🎉 Quiz Completed!</h2>

            {/* 得分 */}
            <div style={styles.scoreDisplay}>
              <span style={styles.scoreBig}>{score}</span>
              <span style={styles.scoreTotal}> / {quizQuestions.length}</span>
            </div>

            {/* 掌握百分比 */}
            <p style={{ textAlign: 'center', fontSize: 15, color: '#555', marginBottom: 16 }}>
              Mastery Level: {Math.round((score / quizQuestions.length) * 100)}%
            </p>

            {/* 掌握程度进度条 */}
            <div style={styles.progressBarBg}>
              <div style={{
                ...styles.progressBarFill,
                width: `${(score / quizQuestions.length) * 100}%`,
                background: score / quizQuestions.length >= 0.8 ? '#16a34a' : '#2563eb'
              }} />
            </div>

            {/* 评价文字 */}
            <p style={{ textAlign: 'center', fontSize: 14, color: '#666', margin: '16px 0' }}>
              {score / quizQuestions.length >= 0.8
                ? '🌟 Great job!'
                : score / quizQuestions.length >= 0.6
                  ? 'Keep studying to improve'
                  : 'Consider reviewing this material'
              }
            </p>

            <button onClick={handleRestartQuiz} style={styles.btn}>
              Try Again
            </button>
          </div>
        )
      }
    </div>

  )
}




const styles = {
  container: {
    maxWidth: 720,
    margin: '0 auto',
    padding: '40px 20px',
    fontFamily: 'sans-serif',
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    marginBottom: 24,
  },
  card: {
    border: '1px solid #e0e0e0',
    borderRadius: 12,
    padding: 20,
    marginBottom: 16,
    background: '#fff',
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: 600,
    marginBottom: 12,
    marginTop: 0,
  },
  status: {
    marginTop: 10,
    fontSize: 14,
    color: '#444',
  },
  summaryBox: {
    background: '#f9f9f9',
    borderRadius: 8,
    padding: '12px 16px',
    marginBottom: 12,
  },
  summaryLabel: {
    fontSize: 12,
    fontWeight: 600,
    color: '#888',
    marginBottom: 6,
    marginTop: 0,
  },
  summaryText: {
    fontSize: 14,
    lineHeight: 1.7,
    color: '#333',
    margin: 0,
  },
  vocabList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
  },
  vocabCard: {
    border: '1px solid #e0e0e0',
    borderRadius: 10,
    padding: '10px 16px',
    background: '#fafafa',
    fontSize: 14,
    fontWeight: 600,
    color: '#1a1a1a',
  },
  historyHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  clearBtn: {
    fontSize: 12,
    padding: '4px 10px',
    cursor: 'pointer',
    border: '1px solid #ccc',
    borderRadius: 6,
    background: '#fff',
  },
  userMsg: {
    background: '#f0f4ff',
    borderRadius: 8,
    padding: '8px 12px',
    marginBottom: 8,
    fontSize: 14,
  },
  aiMsg: {
    background: '#f5f5f5',
    borderRadius: 8,
    padding: '8px 12px',
    marginBottom: 8,
    fontSize: 14,
  },
  sources: {
    fontSize: 13,
    color: '#2563eb',
    marginBottom: 8,
  },
  answerText: {
    fontSize: 15,
    lineHeight: 1.7,
    whiteSpace: 'pre-wrap',
  },
  input: {
    width: '100%',
    padding: '10px 14px',
    fontSize: 15,
    border: '1px solid #ccc',
    borderRadius: 8,
    marginBottom: 10,
    boxSizing: 'border-box',
  },
  btn: {
    padding: '10px 24px',
    fontSize: 15,
    background: '#2563eb',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    cursor: 'pointer',
  },
  btnDisabled: {
    padding: '10px 24px',
    fontSize: 15,
    background: '#9ca3af',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    cursor: 'not-allowed',
  },
  quizProgress: {
    display: 'flex',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  quizProgressText: {
    fontSize: 13,
    color: '#666',
  },
  quizScore: {
    fontSize: 13,
    color: '#2563eb',
    fontWeight: 600,
  },
  progressBarBg: {
    background: '#e5e7eb',
    borderRadius: 99,
    height: 8,
    marginBottom: 20,
  },
  progressBarFill: {
    background: '#2563eb',
    borderRadius: 99,
    height: 8,
    transition: 'width 0.3s ease',
  },
  quizQuestion: {
    fontSize: 16,
    fontWeight: 600,
    lineHeight: 1.6,
    color: '#1a1a1a',
    marginBottom: 16,
  },
  optionsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
  },
  optionBtn: {
    padding: '12px 16px',
    fontSize: 14,
    textAlign: 'left',
    background: '#fff',
    border: '1px solid #d1d5db',
    borderRadius: 8,
    cursor: 'pointer',
  },
  optionSelected: {
    padding: '12px 16px',
    fontSize: 14,
    textAlign: 'left',
    background: '#eff6ff',
    border: '2px solid #2563eb',
    borderRadius: 8,
    cursor: 'pointer',
  },
  optionCorrect: {
    padding: '12px 16px',
    fontSize: 14,
    textAlign: 'left',
    background: '#f0fdf4',
    border: '2px solid #16a34a',
    borderRadius: 8,
    color: '#15803d',
    cursor: 'not-allowed',
  },
  optionWrong: {
    padding: '12px 16px',
    fontSize: 14,
    textAlign: 'left',
    background: '#fef2f2',
    border: '2px solid #dc2626',
    borderRadius: 8,
    color: '#dc2626',
    cursor: 'not-allowed',
  },
  explanation: {
    background: '#f8fafc',
    border: '1px solid #e2e8f0',
    borderRadius: 8,
    padding: '12px 16px',
    marginTop: 16,
    fontSize: 14,
    lineHeight: 1.6,
  },
  scoreDisplay: {
    textAlign: 'center',
    margin: '16px 0',
  },
  scoreBig: {
    fontSize: 56,
    fontWeight: 'bold',
    color: '#2563eb',
  },
  scoreTotal: {
    fontSize: 28,
    color: '#888',
  },
  saveNoteBtn: {
    marginTop: 8,
    padding: '4px 10px',
    fontSize: 12,
    background: '#f3f4f6',
    border: '1px solid #d1d5db',
    borderRadius: 4,
    cursor: 'pointer',
    color: '#374151'
  },
  noteItem: {
    padding: '12px',
    borderBottom: '1px solid #e5e7eb',
    marginBottom: 8
  },
  noteHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    marginBottom: 6,
    fontSize: 12,
    color: '#6b7280'
  },
  noteType: {
    background: '#dbeafe',
    color: '#1e40af',
    padding: '2px 8px',
    borderRadius: 4,
    fontWeight: 500
  },
  noteDate: {
    color: '#9ca3af'
  },
  deleteNoteBtn: {
    marginLeft: 'auto',
    background: 'transparent',
    border: 'none',
    cursor: 'pointer',
    fontSize: 14
  },
  noteContent: {
    fontSize: 14,
    color: '#1f2937'
  },
  courseBar: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '12px 16px',
    background: '#f9fafb',
    borderBottom: '1px solid #e5e7eb',
    marginBottom: 16
  },
  courseSelect: {
    padding: '6px 10px',
    fontSize: 14,
    borderRadius: 6,
    border: '1px solid #d1d5db',
    background: '#fff',
    minWidth: 200,
    cursor: 'pointer'
  },
  btnSmall: {
    padding: '4px 10px',
    fontSize: 12,
    background: '#2563eb',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer'
  },
  btnSmallDanger: {
    padding: '4px 10px',
    fontSize: 12,
    background: '#dc2626',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer'
  }
}

export default App