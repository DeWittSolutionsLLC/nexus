"""
PDF Reader Plugin — Extract text from PDFs and analyze with Ollama.
"""

import os
import logging
import requests
from pathlib import Path
from datetime import datetime, timedelta
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.pdf_reader")

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"


def _ollama(prompt: str, timeout: int = 60) -> str:
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        return resp.json().get("response", "").strip()
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        return f"[Ollama unavailable: {e}]"


def _detect_pdf_lib() -> str:
    """Returns the name of the first available PDF library."""
    try:
        import fitz  # noqa: F401
        return "fitz"
    except ImportError:
        pass
    try:
        import pdfplumber  # noqa: F401
        return "pdfplumber"
    except ImportError:
        pass
    try:
        import pypdf  # noqa: F401
        return "pypdf"
    except ImportError:
        pass
    return "none"


def _extract_text(pdf_path: str, page_num: int = None) -> tuple[str, int]:
    """Extract text from a PDF file. Returns (text, page_count)."""
    lib = _detect_pdf_lib()
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Not a PDF file: {pdf_path}")

    if lib == "fitz":
        import fitz
        doc = fitz.open(str(path))
        total = doc.page_count
        if page_num is not None:
            if page_num < 1 or page_num > total:
                raise ValueError(f"Page {page_num} out of range (1–{total})")
            page = doc[page_num - 1]
            return page.get_text(), total
        text = "\n".join(doc[i].get_text() for i in range(total))
        doc.close()
        return text, total

    elif lib == "pdfplumber":
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            total = len(pdf.pages)
            if page_num is not None:
                if page_num < 1 or page_num > total:
                    raise ValueError(f"Page {page_num} out of range (1–{total})")
                return pdf.pages[page_num - 1].extract_text() or "", total
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        return text, total

    elif lib == "pypdf":
        import pypdf
        reader = pypdf.PdfReader(str(path))
        total = len(reader.pages)
        if page_num is not None:
            if page_num < 1 or page_num > total:
                raise ValueError(f"Page {page_num} out of range (1–{total})")
            return reader.pages[page_num - 1].extract_text() or "", total
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
        return text, total

    else:
        raise ImportError("No PDF library found. Install PyMuPDF (fitz), pdfplumber, or pypdf.")


class PdfReaderPlugin(BasePlugin):
    name = "pdf_reader"
    description = "Read, extract text from, and analyze PDF files with AI"
    icon = "📄"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._pdf_lib = "none"

    async def connect(self) -> bool:
        self._pdf_lib = _detect_pdf_lib()
        if self._pdf_lib == "none":
            self._status_message = "No PDF library — install PyMuPDF, pdfplumber, or pypdf"
            logger.warning("No PDF library available")
        else:
            self._status_message = f"Ready (using {self._pdf_lib})"
            logger.info(f"PDF reader using: {self._pdf_lib}")
        self._connected = True
        return True

    async def execute(self, action: str, params: dict) -> str:
        actions = {
            "read_pdf": self._read_pdf,
            "summarize_pdf": self._summarize_pdf,
            "ask_pdf": self._ask_pdf,
            "extract_tables": self._extract_tables,
            "list_recent_pdfs": self._list_recent_pdfs,
            "get_page": self._get_page,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown action: {action}. Available: {', '.join(actions)}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "read_pdf", "description": "Extract all text from a PDF file", "params": ["path"]},
            {"action": "summarize_pdf", "description": "AI-generated summary of a PDF", "params": ["path"]},
            {"action": "ask_pdf", "description": "Ask a question about a PDF's content", "params": ["path", "question"]},
            {"action": "extract_tables", "description": "Find and extract tables from a PDF", "params": ["path"]},
            {"action": "list_recent_pdfs", "description": "List recent PDFs from Downloads and Desktop", "params": []},
            {"action": "get_page", "description": "Extract text from a specific page", "params": ["path", "page"]},
        ]

    async def _read_pdf(self, params: dict) -> str:
        path = params.get("path", "").strip()
        if not path:
            return "Please provide a PDF 'path'."
        try:
            text, total = _extract_text(path)
            if not text.strip():
                return f"PDF has {total} page(s) but no extractable text (may be scanned/image-based)."
            preview = text[:3000]
            note = f"\n\n[Showing first 3000 of {len(text)} characters]" if len(text) > 3000 else ""
            return f"PDF: {Path(path).name}  ({total} pages)\n{'─' * 40}\n{preview}{note}"
        except (FileNotFoundError, ValueError, ImportError) as e:
            return f"Error: {e}"
        except Exception as e:
            logger.error(f"read_pdf error: {e}")
            return f"Failed to read PDF: {e}"

    async def _summarize_pdf(self, params: dict) -> str:
        path = params.get("path", "").strip()
        if not path:
            return "Please provide a PDF 'path'."
        try:
            text, total = _extract_text(path)
        except (FileNotFoundError, ValueError, ImportError) as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Failed to read PDF: {e}"

        if not text.strip():
            return "PDF contains no extractable text (may be image-based)."

        context = text[:5000]
        prompt = (
            f"Summarize the following PDF document clearly and concisely. "
            f"Include the main topics, key points, and any important conclusions.\n\n"
            f"Document: {Path(path).name}\n\n{context}"
        )
        summary = _ollama(prompt, timeout=90)
        return f"Summary: {Path(path).name}  ({total} pages)\n{'─' * 40}\n{summary}"

    async def _ask_pdf(self, params: dict) -> str:
        path = params.get("path", "").strip()
        question = params.get("question", "").strip()
        if not path or not question:
            return "Please provide both 'path' and 'question'."
        try:
            text, total = _extract_text(path)
        except (FileNotFoundError, ValueError, ImportError) as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Failed to read PDF: {e}"

        if not text.strip():
            return "PDF contains no extractable text."

        context = text[:6000]
        prompt = (
            f"Based on the following document content, answer this question: {question}\n\n"
            f"Document ({Path(path).name}):\n{context}\n\n"
            f"Answer:"
        )
        answer = _ollama(prompt, timeout=90)
        return f"Q: {question}\n\nA: {answer}"

    async def _extract_tables(self, params: dict) -> str:
        path = params.get("path", "").strip()
        if not path:
            return "Please provide a PDF 'path'."

        lib = _detect_pdf_lib()
        if lib == "pdfplumber":
            import pdfplumber
            try:
                tables_found = []
                with pdfplumber.open(path) as pdf:
                    for i, page in enumerate(pdf.pages, 1):
                        tables = page.extract_tables()
                        for j, table in enumerate(tables, 1):
                            rows = [" | ".join(str(c) if c else "" for c in row) for row in table]
                            tables_found.append(f"Page {i}, Table {j}:\n" + "\n".join(rows))
                if not tables_found:
                    return "No tables detected in this PDF."
                return f"Tables found in {Path(path).name}:\n\n" + "\n\n".join(tables_found[:5])
            except Exception as e:
                return f"Table extraction error: {e}"
        elif lib == "fitz":
            # fitz doesn't natively extract tables; fall back to text and use AI
            try:
                text, total = _extract_text(path)
                prompt = (
                    f"Extract and format any tables from the following document text. "
                    f"Present each table clearly with aligned columns:\n\n{text[:4000]}"
                )
                result = _ollama(prompt)
                return f"Tables extracted (via AI) from {Path(path).name}:\n\n{result}"
            except Exception as e:
                return f"Table extraction error: {e}"
        else:
            try:
                text, _ = _extract_text(path)
                prompt = f"Find and format any tables in this document:\n\n{text[:4000]}"
                return _ollama(prompt)
            except Exception as e:
                return f"Error: {e}"

    async def _list_recent_pdfs(self, params: dict) -> str:
        search_dirs = [
            Path.home() / "Downloads",
            Path.home() / "Desktop",
            Path.home() / "Documents",
        ]
        cutoff = datetime.now() - timedelta(days=30)
        found = []
        for d in search_dirs:
            if d.exists():
                try:
                    for f in d.rglob("*.pdf"):
                        try:
                            mtime = datetime.fromtimestamp(f.stat().st_mtime)
                            if mtime >= cutoff:
                                found.append((mtime, f))
                        except OSError:
                            pass
                except PermissionError:
                    pass

        if not found:
            return "No PDFs found in Downloads, Desktop, or Documents from the last 30 days."

        found.sort(key=lambda x: x[0], reverse=True)
        lines = [f"Recent PDFs (last 30 days):\n"]
        for mtime, f in found[:20]:
            size_kb = f.stat().st_size // 1024
            lines.append(f"  {mtime.strftime('%Y-%m-%d')}  {f.name}  ({size_kb} KB)")
            lines.append(f"    {f}")
        return "\n".join(lines)

    async def _get_page(self, params: dict) -> str:
        path = params.get("path", "").strip()
        page = params.get("page", 1)
        if not path:
            return "Please provide a PDF 'path'."
        try:
            page_num = int(page)
        except (TypeError, ValueError):
            return "Page number must be an integer."
        try:
            text, total = _extract_text(path, page_num=page_num)
            if not text or not text.strip():
                return f"Page {page_num} of {Path(path).name} appears to have no extractable text."
            return f"{Path(path).name} — Page {page_num} of {total}\n{'─' * 40}\n{text}"
        except (FileNotFoundError, ValueError, ImportError) as e:
            return f"Error: {e}"
        except Exception as e:
            logger.error(f"get_page error: {e}")
            return f"Failed to read page: {e}"
