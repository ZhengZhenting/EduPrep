import { useState } from 'react'
import axios from 'axios'

const API = 'http://localhost:8000'  // 对接后端API地址

function App() {
  // 状态管理
  const [uploadStatus, setUploadStatus] = useState('')
  const [filename, setFilename] = useState('')    
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [uploading, setUploading] = useState(false)
  const [asking, setAsking] = useState(false)


  // 处理PDF上传Upload
  const handleUpload = async (e) => { //e 是事件对象，里面包含用户选的文件,async 表示这个函数要等待网络请求，不会卡住页面。
    const file = e.target.files[0] // 获取用户选的第一个文件files[0]
    if (!file) return //如果用户没有选文件就关掉了弹窗，直接退出，什么都不做。

    setUploading(true)
    setUploadStatus('uploading')

    const formData = new FormData()
    formData.append('file', file) //这个名字必须和后端完全一致 — 后端写的是 file: UploadFile = File(...)，所以前端这里也必须叫 'file'

    try {
      const res = await axios.post(`${API}/upload`, formData) //await 表示等待后端处理完毕再继续执行下一行。
      setFilename(res.data.filename)  //这里取出 filename 存起来，因为下面提问时需要告诉后端是哪个文件
      setUploadStatus(`File ${res.data.filename} successfully uploaded, ${res.data.pages} pages in total`) //后端返回的JSON里面的字段见后端的 upload() 函数 return {'filename': filename, 'pages': num_pages......}
    } catch (err) {
      setUploadStatus(`Upload failed: ${err.message}`)
    }

    setUploading(false)
  }

  // 处理提问Ask
  const handleAsk = async (e) => {
    if (!question.trim()) return
    if (!filename) {
      setAnswer('Please upload a PDF first.')
      return
    }

    setAsking(true)
    setAnswer('thinking...')

    try {
      const res = await axios.post(`${API}/ask`, {
        question: question,
        filename: filename
      })
      setAnswer(res.data.answer)
    } catch (err) {
      setAnswer(`Error: ${err.message}`)
    }

    setAsking(false)
  }

  //处理回车键提问
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !asking) {
      handleAsk()
    }
  }




  // HTML
  return (
    <div style={styles.container}>
      <h1 style={styles.title}>📚 EduPrep</h1>
      <p style={styles.subtitle}>uploadPDF，using AI to help you understand</p>

      {/* 上传区域 */}
      <div style={styles.card}>
        <h2 style={styles.cardTitle}>First Step: Upload a PDF File</h2>
        <input
          type="file"
          accept=".pdf"
          onChange={handleUpload}
          disabled={uploading}
          style={styles.fileInput}
        />
        {uploadStatus && (
          <p style={styles.statusText}>{uploadStatus}</p>
        )}
      </div>

      {/* 提问区域 */}
      <div style={styles.card}>
        <h2 style={styles.cardTitle}>Second Step: Ask A Question</h2>
        <input
          type="text"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="input your question..."
          disabled={asking}
          style={styles.input}
        />
        <button
          onClick={handleAsk}
          disabled={asking || !filename}
          style={asking || !filename ? styles.buttonDisabled : styles.button}
        >
          {asking ? 'thinking...' : 'asking'}
        </button>
      </div>


      {/* 回答区域 */}
      {answer && (
        <div style={styles.card}>
          <h2 style={styles.cardTitle}>Answer from AI</h2>
          <p style={styles.answerText}>{answer}</p>
        </div>
      )}
    </div>
  )
}





// Styles
const styles = {
  container: {
    maxWidth: '720px',
    margin: '0 auto',
    padding: '40px 20px',
    fontFamily: 'sans-serif',
  },
  title: {
    fontSize: '32px',
    fontWeight: 'bold',
    marginBottom: '8px',
    color: '#1a1a1a',
  },
  subtitle: {
    fontSize: '16px',
    color: '#666',
    marginBottom: '32px',
  },
  card: {
    border: '1px solid #e0e0e0',
    borderRadius: '12px',
    padding: '24px',
    marginBottom: '20px',
    backgroundColor: '#fff',
  },
  cardTitle: {
    fontSize: '18px',
    fontWeight: '600',
    marginBottom: '16px',
    color: '#1a1a1a',
  },
  fileInput: {
    fontSize: '14px',
    color: '#333',
  },
  statusText: {
    marginTop: '12px',
    fontSize: '14px',
    color: '#444',
  },
  input: {
    width: '100%',
    padding: '10px 14px',
    fontSize: '15px',
    border: '1px solid #ccc',
    borderRadius: '8px',
    marginBottom: '12px',
    boxSizing: 'border-box',
  },
  button: {
    padding: '10px 24px',
    fontSize: '15px',
    backgroundColor: '#2563eb',
    color: '#fff',
    border: 'none',
    borderRadius: '8px',
    cursor: 'pointer',
  },
  buttonDisabled: {
    padding: '10px 24px',
    fontSize: '15px',
    backgroundColor: '#9ca3af',
    color: '#fff',
    border: 'none',
    borderRadius: '8px',
    cursor: 'not-allowed',
  },
  answerText: {
    fontSize: '15px',
    lineHeight: '1.7',
    color: '#333',
    whiteSpace: 'pre-wrap',   // 保留换行格式
  },
}

export default App