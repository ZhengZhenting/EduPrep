import { useState } from 'react'

const API = 'http://localhost:8000'  // 对接后端API地址

function App() {
  // 状态管理
  const [uploadStatus, setUploadStatus] = useState('')
  const [filename, setFilename] = useState('')
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [sources, setSources] = useState([])      // 页码来源
  const [history, setHistory] = useState([])      // 对话历史
  const [uploading, setUploading] = useState(false)
  const [asking, setAsking] = useState(false)
  const [previewData, setPreviewData] = useState(null)   // 存储preview返回的数据
  const [previewing, setPreviewing] = useState(false)     // 是否正在加载


  // 处理PDF上传Upload
  const handleUpload = async (e) => { //e 是事件对象，里面包含用户选的文件,async 表示这个函数要等待网络请求，不会卡住页面。
    const file = e.target.files[0] // 获取用户选的第一个文件files[0]
    if (!file) return //如果用户没有选文件就关掉了弹窗，直接退出，什么都不做。

    setUploading(true)
    setUploadStatus('uploading...')

    const formData = new FormData()
    formData.append('file', file) //这个名字必须和后端完全一致 — 后端写的是 file: UploadFile = File(...)，所以前端这里也必须叫 'file'

    try {
      const res = await fetch(`${API}/upload`, {
        method: 'POST',
        body: formData
      })
      const data = await res.json()
      setFilename(data.filename)  //这里取出 filename 存起来，因为下面提问时需要告诉后端是哪个文件
      setUploadStatus(`File ${data.filename} successfully uploaded, ${data.chunks} chunks in total`) //后端返回的JSON里面的字段见后端的 upload() 函数 return {'filename': filename, 'chunks': num_chunks......}
      setHistory([]) //上传新文件后清空对话历史
    } catch (err) {
      setUploadStatus(`Upload failed: ${err.message}`)
    }

    setUploading(false)
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
          filename: filename
        })
      })

      const data = await response.json()

      setAnswer(data.answer)
      setSources(data.sources)

      // 保存历史，sources直接从data里取
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
        body: JSON.stringify({ filename: filename })
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

  // HTML
  return (
    <div style={styles.container}>
      <h1 style={styles.title}>📚 EduPrep</h1>

      {/* 上传区域 */}
      <div style={styles.card}>
        <h2 style={styles.cardTitle}>Upload PDF</h2>
        <input type="file" accept=".pdf" onChange={handleUpload} disabled={uploading} />
        {uploadStatus && <p style={styles.status}>{uploadStatus}</p>}
      </div>

      {/* Preview 触发按钮 */}
      <div style={styles.card}>
        <h2 style={styles.cardTitle}>📋 Preview Mode</h2>
        <p style={{ fontSize: 14, color: '#666', marginBottom: 12, marginTop: 0 }}>
          Automatically generate lecture notes summary and key vocabulary list
        </p>
        <button
          onClick={handlePreview}
          disabled={!filename || previewing}
          style={!filename || previewing ? styles.btnDisabled : styles.btn}
        >
          {previewing ? 'Generating, please wait...' : 'Generate Preview'}
        </button>
      </div>

      {/* Preview 结果 */}
      {previewData && (
        <div style={styles.card}>

          {/* 双语摘要 */}
          <h2 style={styles.cardTitle}>📝 Summary</h2>

          <div style={styles.summaryBox}>
            <p style={styles.summaryLabel}>🇩🇪 Deutsch</p>
            <p style={styles.summaryText}>{previewData.summary_de}</p>
          </div>

          <div style={{ ...styles.summaryBox, background: '#f0f9ff' }}>
            <p style={styles.summaryLabel}>🇨🇳 中文</p>
            <p style={styles.summaryText}>{previewData.summary_zh}</p>
          </div>

          {/* 词汇列表 */}
          <h2 style={{ ...styles.cardTitle, marginTop: 24 }}>🔑 Key Words</h2>

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
              {msg.content}
              {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                <div style={{ fontSize: 12, color: '#2563eb', marginTop: 4 }}>
                  📄 Sources from Page： {msg.sources.join('、')}
                </div>
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
              📄 Sources from Page： {sources.join('、')}
            </p>
          )}
          <p style={styles.answerText}>{answer}</p>
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
          disabled={asking || !filename}
          style={styles.input}
        />
        <button
          onClick={handleAsk}
          disabled={asking || !filename}
          style={asking || !filename ? styles.btnDisabled : styles.btn}
        >
          {asking ? 'Answering...' : 'Ask'}
        </button>
      </div>
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
}

export default App