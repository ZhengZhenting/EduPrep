"""Render a page to an image and transcribe it to clean text via Claude vision.

Used for pages triaged as 'vision': 
formula -> LaTeX, 
diagram -> text description,
table -> structured. """

from __future__ import annotations
import base64
import os
import fitz
import anthropic
from dotenv import load_dotenv

load_dotenv() # 读取 .env → 灌进环境变量

VISION_MODEL = "claude-sonnet-4-5"   # lower model is sufficient for extraction task
RENDER_DPI   = 150                   # resolution 150 is enough to read formulas
_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY")) # 从环境变量里取出来env里面的密钥使用

_VISION_PROMPT = """You are a lecture-digitization assistant. This is an image of one lecture slide/page. Transcribe the body content into plain text for retrieval.

Rules:
- Math formulas -> transcribe as LaTeX (wrap in $...$)
- Charts/diagrams/flowcharts -> objectively describe the content and relationships in a paragraph
- Images/photos -> briefly describe their content
- Tables -> preserve the row/column structure in text (Markdown table is fine)
- Keep the body's original language; do NOT translate
- Ignore headers, footers, page numbers, section navigation, professor names, university logos, and other elements that repeat on every page
- Output only the transcribed content itself, with no explanation or wrapper text"""

def render_page_to_png(page: "fitz.Page", dpi: int = RENDER_DPI) -> bytes:
    pix = page.get_pixmap(dpi=dpi)
    return pix.tobytes("png")

def transcribe_page(png_bytes: bytes) -> str:
    # 图片(PNG)本质是一堆二进制字节——里面有各种乱七八糟、无法直接当文字的字节。但 Claude 的 API 是通过 JSON(纯文本)传输的,JSON 里塞不进原始二进制。
    # base64把图片的二进制字节,用 base64 规则编码成一串只由 A-Z a-z 0-9 + / 组成的安全文本,这串文本就能放进 JSON 发出去。Claude 那边再解码还原成图片
    b64 = base64.standard_b64encode(png_bytes).decode("utf-8") 
    resp = _client.messages.create(
        model=VISION_MODEL,
        max_tokens=1500,
        temperature=0,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": _VISION_PROMPT},
            ],
        }],
    )
    return resp.content[0].text.strip()