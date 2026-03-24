from core.plugin_manager import BasePlugin
import logging, json, uuid, re, requests
from pathlib import Path
from datetime import datetime
from collections import Counter

logger = logging.getLogger("nexus.plugins.local_rag")

INDEX_FILE = Path.home() / "NexusScripts" / "rag_index.json"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"
CHUNK_SIZE = 500

try:
    import PyPDF2
    HAS_PDF = True
except ImportError:
    try:
        import pdfplumber
        HAS_PDF = True
        PyPDF2 = None
    except ImportError:
        HAS_PDF = False
        PyPDF2 = None


def _ollama(prompt: str) -> str:
    try:
        resp = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}, timeout=90)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        return f"[Ollama error: {e}]"


def _load_index() -> list:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_index(data: list):
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        if PyPDF2:
            try:
                with open(path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    return "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception as e:
                return f"[PDF read error: {e}]"
        try:
            import pdfplumber
            with pdfplumber.open(str(path)) as pdf:
                return "\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception as e:
            return f"[PDF read error: {e}]"
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[Read error: {e}]"


def _chunk_text(text: str) -> list[dict]:
    chunks = []
    paragraphs = re.split(r"\n\s*\n", text)
    current = ""
    start = 0
    pos = 0
    for para in paragraphs:
        if len(current) + len(para) > CHUNK_SIZE and current:
            chunks.append({"text": current.strip(), "start_char": start})
            start = pos
            current = para
        else:
            current = (current + "\n\n" + para).strip() if current else para
        pos += len(para) + 2
    if current.strip():
        chunks.append({"text": current.strip(), "start_char": start})
    if not chunks and text.strip():
        for i in range(0, len(text), CHUNK_SIZE):
            chunks.append({"text": text[i:i + CHUNK_SIZE].strip(), "start_char": i})
    return chunks


def _stopwords() -> set:
    return {"the", "a", "an", "is", "in", "on", "at", "to", "of", "and", "or", "for",
            "with", "it", "this", "that", "are", "was", "be", "by", "from", "as", "i",
            "you", "he", "she", "we", "they", "do", "not", "have", "what", "how", "can"}


def _score_chunk(query_words: set, chunk_text: str) -> float:
    stop = _stopwords()
    chunk_words = set(re.findall(r"\w+", chunk_text.lower())) - stop
    q = query_words - stop
    if not q or not chunk_words:
        return 0.0
    overlap = q & chunk_words
    return len(overlap) / (len(q | chunk_words) + 1e-9)


class LocalRagPlugin(BasePlugin):
    name = "local_rag"
    description = "Index local documents and answer questions using retrieval-augmented generation."
    icon = "🔍"

    async def connect(self) -> bool:
        INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._connected = True
        idx = _load_index()
        self._status_message = f"Ready ({len(idx)} documents indexed)"
        return True

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "index_file", "description": "Index a text file or PDF into the RAG store", "params": ["path"]},
            {"action": "index_folder", "description": "Index all matching files in a folder", "params": ["path", "extensions"]},
            {"action": "query", "description": "Ask a question answered from indexed documents", "params": ["question", "top_k"]},
            {"action": "list_indexed", "description": "Show all indexed documents", "params": []},
            {"action": "remove_from_index", "description": "Remove a document from the index by path or id", "params": ["path", "id"]},
            {"action": "clear_index", "description": "Remove all indexed documents", "params": []},
            {"action": "reindex_all", "description": "Re-read all files and rebuild the index", "params": []},
        ]

    async def execute(self, action: str, params: dict) -> str:
        try:
            if action == "index_file":
                return await self._index_file(params)
            elif action == "index_folder":
                return await self._index_folder(params)
            elif action == "query":
                return await self._query(params)
            elif action == "list_indexed":
                return await self._list_indexed(params)
            elif action == "remove_from_index":
                return await self._remove_from_index(params)
            elif action == "clear_index":
                return await self._clear_index(params)
            elif action == "reindex_all":
                return await self._reindex_all(params)
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.exception("LocalRAG error")
            return f"Error in local_rag.{action}: {e}"

    def _index_single(self, path: Path, index: list) -> str:
        existing = next((d for d in index if d["path"] == str(path)), None)
        if existing:
            index.remove(existing)
        text = _read_file(path)
        if text.startswith("["):
            return f"Failed to read {path.name}: {text}"
        chunks = _chunk_text(text)
        doc = {
            "id": str(uuid.uuid4())[:8],
            "path": str(path),
            "title": path.name,
            "chunks": chunks,
            "indexed_at": datetime.now().isoformat(),
        }
        index.append(doc)
        return f"Indexed '{path.name}' ({len(chunks)} chunks)"

    async def _index_file(self, params: dict) -> str:
        path_str = params.get("path", "").strip()
        if not path_str:
            return "No path provided."
        path = Path(path_str)
        if not path.exists():
            return f"File not found: {path_str}"
        index = _load_index()
        result = self._index_single(path, index)
        _save_index(index)
        return result

    async def _index_folder(self, params: dict) -> str:
        path_str = params.get("path", "").strip()
        extensions = params.get("extensions", [".txt", ".md", ".py"])
        if not path_str:
            return "No path provided."
        folder = Path(path_str)
        if not folder.is_dir():
            return f"Not a directory: {path_str}"
        index = _load_index()
        results = []
        files = [f for f in folder.rglob("*") if f.is_file() and f.suffix.lower() in extensions]
        for f in files:
            results.append(self._index_single(f, index))
        _save_index(index)
        return f"Indexed {len(files)} file(s) from {path_str}:\n" + "\n".join(f"  {r}" for r in results)

    async def _query(self, params: dict) -> str:
        question = params.get("question", "").strip()
        top_k = int(params.get("top_k", 3))
        if not question:
            return "No question provided."
        index = _load_index()
        if not index:
            return "No documents indexed. Use index_file or index_folder first."
        query_words = set(re.findall(r"\w+", question.lower()))
        scored = []
        for doc in index:
            for chunk in doc.get("chunks", []):
                score = _score_chunk(query_words, chunk["text"])
                scored.append((score, chunk["text"], doc["title"]))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]
        if not top or top[0][0] == 0:
            return "No relevant content found in indexed documents."
        context = "\n\n".join(f"[From: {title}]\n{text}" for _, text, title in top)
        prompt = f"Based on the following documents:\n{context}\n\nAnswer this question clearly and concisely: {question}"
        answer = _ollama(prompt)
        sources = list(dict.fromkeys(title for _, _, title in top))
        return f"Answer:\n{answer}\n\nSources: {', '.join(sources)}"

    async def _list_indexed(self, params: dict) -> str:
        index = _load_index()
        if not index:
            return "No documents indexed."
        lines = [f"Indexed Documents ({len(index)}):"]
        for doc in index:
            lines.append(f"  [{doc['id']}] {doc['title']} — {len(doc.get('chunks', []))} chunks (indexed: {doc['indexed_at'][:10]})")
            lines.append(f"       Path: {doc['path']}")
        return "\n".join(lines)

    async def _remove_from_index(self, params: dict) -> str:
        path_str = params.get("path", "").strip()
        doc_id = params.get("id", "").strip()
        index = _load_index()
        original_len = len(index)
        if path_str:
            index = [d for d in index if d["path"] != path_str]
        elif doc_id:
            index = [d for d in index if d["id"] != doc_id]
        else:
            return "Provide path or id."
        if len(index) == original_len:
            return "Document not found in index."
        _save_index(index)
        return f"Removed document from index. ({original_len - len(index)} removed)"

    async def _clear_index(self, params: dict) -> str:
        _save_index([])
        return "Index cleared."

    async def _reindex_all(self, params: dict) -> str:
        index = _load_index()
        paths = [Path(d["path"]) for d in index]
        new_index = []
        results = []
        for path in paths:
            if path.exists():
                results.append(self._index_single(path, new_index))
            else:
                results.append(f"Skipped (not found): {path}")
        _save_index(new_index)
        return f"Reindexed {len(paths)} document(s):\n" + "\n".join(f"  {r}" for r in results)
