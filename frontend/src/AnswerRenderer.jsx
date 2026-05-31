import { useEffect, useRef } from 'react'
import katex from 'katex'
import hljs from 'highlight.js'
import mermaid from 'mermaid'

//文件结构：
//parseAnswer(text)        ← 解析器：把文本拆成片段数组

//TextSegment              ← 渲染普通文字
//MermaidSegment           ← 渲染 Mermaid 图表
//LatexSegment             ← 渲染 LaTeX 公式
//CodeSegment              ← 渲染代码块（带高亮）

//AnswerRenderer           ← 总入口：调用解析器 → 分发给子组件



// 初始化 Mermaid
mermaid.initialize({ startOnLoad: false, theme: 'default' })

// parseAnswer(text) 解析器：把文本拆成片段数组
function parseAnswer(text) {
    const segments = []

    const pattern = /```(mermaid|(\w*))\n([\s\S]*?)```|\$\$([\s\S]*?)\$\$/g

    let lastIndex = 0
    let match

    while ((match = pattern.exec(text)) !== null) { //`pattern.exec(text)` 每次调用会返回下一个匹配结果，没有更多匹配时返回 `null`，循环结束
        if (match.index > lastIndex) { //`match.index` 是mermaid块开始，`lastIndex` 是上次处理完的位置
            const palinText = text.slice(lastIndex, match.index)
            if (palinText.trim()) {
                segments.push({ type: 'text', content: palinText }) //保存特殊块之前的普通文字
            }
        }

        if (match[1] === 'mermaid') { //`match[1]` 是语言名
            segments.push({ type: 'mermaid', content: match[3].trim() }) //`match[3]`（代码内容）
        } else if (match[4] !== undefined) {
            segments.push({ type: 'latex', content: match[4].trim() }) //`match[4]` 是 LaTeX 内容
        } else {
            segments.push({
                type: 'code',
                language: match[2] || 'plaintext', //`match[2]` 是代码块指定的语言
                content: match[3]
            })
        }
        lastIndex = pattern.lastIndex
    }
    if (lastIndex < text.length) {
        const remaining = text.slice(lastIndex)
        if (remaining.trim()) {
            segments.push({ type: 'text', content: remaining })
        }
    }
    return segments
}


// 各类型的渲染子组件
// 普通文字
function TextSegment({ content }) {
    return (
        <p style={{ fontSize: 15, lineHeight: 1.8, whiteSpace: 'pre-wrap', margin: '8px 0' }}>
            {content}
        </p>
    )
}
// Mermaid 图表
function MermaidSegment({ content }) {
    const ref = useRef(null)

    useEffect(() => {
        if (!ref.current) return

        const container = ref.current
        container.innerHTML = ''

        let cancelled = false
        const id = `mermaid-${Date.now()}-${Math.random().toString(36).slice(2)}`

        mermaid.render(id, content)
            .then(({ svg }) => {
                if (!cancelled && container) container.innerHTML = svg
            })
            .catch((err) => {
                if (!cancelled && container)
                    container.innerHTML = `<pre style="color:red;font-size:12px">Mermaid error: ${err.message}</pre>`
            })

        return () => { cancelled = true }
    }, [content])
    return (
        <div
            ref={ref}
            style={{
                background: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: 8,
                padding: 16,
                margin: '12px 0',
                overflowX: 'auto'
            }}
        />
    )
}
// LaTeX 数学公式
function LatexSegment({ content }) {
    let html = ''
    try {
        html = katex.renderToString(content, { displayMode: true, throwOnError: false })
    } catch (e) {
        html = `<span style="color:red">failed:${e.message}</span>`
    }

    return (
        <div
            dangerouslySetInnerHTML={{ __html: html }}
            style={{
                background: '#fafafa',
                border: '1px solid #e2e8f0',
                borderRadius: 8,
                padding: '12px 20px',
                margin: '12px 0',
                overflowX: 'auto',
                textAlign: 'center'
            }}
        />
    )
}
// 代码块
function CodeSegment({ content, language }) {
    const ref = useRef(null)

    useEffect(() => {
        if (ref.current) {
            ref.current.removeAttribute('data-highlighted')
            hljs.highlightElement(ref.current)
        }
    }, [content])
    return (
        <div style={{ margin: '12px 0', borderRadius: 8, overflow: 'hidden' }}>
            {/* 语言标签栏 */}
            <div style={{
                background: '#1e293b',
                color: '#94a3b8',
                fontSize: 12,
                padding: '4px 12px'
            }}>
                {language}
            </div>
            <pre style={{ margin: 0 }}>
                <code ref={ref} className={`language-${language}`}>
                    {content}
                </code>
            </pre>
        </div>
    )
}


// 第三步：接收完整的answer文本，调用解析器，再分发给各子组件
export default function AnswerRenderer({ text }) {
    if (!text) return null

    const segments = parseAnswer(text)
    return (
        <div>
            {segments.map((seg, index) => {
                if (seg.type === 'mermaid') return <MermaidSegment key={index} content={seg.content} />
                if (seg.type === 'latex') return <LatexSegment key={index} content={seg.content} />
                if (seg.type === 'code') return <CodeSegment key={index} content={seg.content} language={seg.language} />
                return <TextSegment key={index} content={seg.content} />
            })}
        </div>
    )
}