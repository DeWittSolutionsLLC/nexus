"""
Auto Documenter Plugin — JARVIS reads any codebase and writes documentation.

"Document my nexus project" → reads every .py file → generates README + docstrings.
"Document C:/Projects/myapp" → full API docs for any folder.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.auto_documenter")

DOCS_DIR = Path.home() / "NexusDocs"

SUPPORTED_EXTENSIONS = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".jsx": "React JSX", ".tsx": "React TSX", ".java": "Java",
    ".go": "Go", ".rs": "Rust", ".cpp": "C++", ".c": "C",
    ".cs": "C#", ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
}

README_SYSTEM_PROMPT = """You are a technical writer. Analyze the provided code files and generate clear, professional documentation.

Write in Markdown. Be concise but complete. Include:
- What the project/file does
- Key classes/functions and their purpose
- How to use it
- Any important notes

Do NOT include the source code itself. Focus on explanation."""


class AutoDocumenterPlugin(BasePlugin):
    name = "auto_documenter"
    description = "AI-powered code documentation — generates README and docs from any codebase"
    icon = "📝"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._ollama_host = config.get("ollama_host", "http://localhost:11434")
        self._model = config.get("model", "llama3.1:8b")
        DOCS_DIR.mkdir(exist_ok=True)

    async def connect(self) -> bool:
        self._connected = True
        self._status_message = "Ready"
        return True

    async def execute(self, action: str, params: dict) -> str:
        dispatch = {
            "document_folder": self._document_folder,
            "document_file":   self._document_file,
            "generate_readme": self._generate_readme,
            "summarize_code":  self._summarize_code,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"❌ Unknown action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "document_folder", "description": "Generate full documentation for a code folder", "params": ["path", "output"]},
            {"action": "document_file",   "description": "Document a single code file", "params": ["path"]},
            {"action": "generate_readme", "description": "Generate a README.md for a project folder", "params": ["path"]},
            {"action": "summarize_code",  "description": "Summarize what a piece of code does", "params": ["path"]},
        ]

    # ── Actions ──────────────────────────────────────────────────────────────

    async def _document_folder(self, params: dict) -> str:
        folder = Path(params.get("path", ".")).resolve()
        output = params.get("output", "")

        if not folder.exists() or not folder.is_dir():
            return f"❌ Folder not found: {folder}"

        # Collect all code files
        files = []
        for ext in SUPPORTED_EXTENSIONS:
            files.extend(folder.rglob(f"*{ext}"))

        # Exclude common noise
        files = [f for f in files if not any(
            part in f.parts for part in ["__pycache__", "node_modules", ".git", "venv", ".venv", "dist", "build"]
        )]

        if not files:
            return f"❌ No supported code files found in {folder}"

        # Limit to 30 files to stay within context
        if len(files) > 30:
            files = files[:30]
            truncated = True
        else:
            truncated = False

        # Build context from files
        context_parts = []
        total_chars = 0
        MAX_CHARS = 12000

        for f in files:
            if total_chars >= MAX_CHARS:
                break
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                rel_path = f.relative_to(folder)
                snippet = content[:1500] + ("..." if len(content) > 1500 else "")
                context_parts.append(f"### {rel_path}\n```{SUPPORTED_EXTENSIONS.get(f.suffix, '')}\n{snippet}\n```")
                total_chars += len(snippet)
            except Exception:
                continue

        context = "\n\n".join(context_parts)

        # Generate docs via Ollama
        prompt = (
            f"Project: {folder.name}\n"
            f"Files analyzed: {len(context_parts)} of {len(files)}\n\n"
            f"Code:\n{context}\n\n"
            f"Generate comprehensive documentation for this project."
        )

        docs = await self._ask_ollama(prompt)
        if not docs:
            return "❌ Failed to generate documentation — is Ollama running?"

        # Save output
        out_dir = Path(output) if output else DOCS_DIR
        out_dir.mkdir(exist_ok=True)
        doc_file = out_dir / f"{folder.name}_docs_{datetime.now().strftime('%Y%m%d')}.md"
        doc_file.write_text(docs, encoding="utf-8")

        note = f"\n⚠️ (Analyzed {len(context_parts)}/{len(files)} files — truncated)" if truncated else ""
        return (
            f"✅ Documentation generated for '{folder.name}', sir.{note}\n\n"
            f"📄 {doc_file}\n\n"
            f"Preview:\n{docs[:500]}..."
        )

    async def _document_file(self, params: dict) -> str:
        path = Path(params.get("path", "")).resolve()
        if not path.exists():
            return f"❌ File not found: {path}"

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return f"❌ Could not read file: {e}"

        lang = SUPPORTED_EXTENSIONS.get(path.suffix, "code")
        prompt = f"Document this {lang} file '{path.name}':\n\n```{lang.lower()}\n{content[:4000]}\n```"
        docs = await self._ask_ollama(prompt)
        if not docs:
            return "❌ Failed to document file — is Ollama running?"

        out_file = DOCS_DIR / f"{path.stem}_docs.md"
        out_file.write_text(docs, encoding="utf-8")
        return f"✅ File documented, sir.\n\n📄 {out_file}\n\n{docs[:600]}..."

    async def _generate_readme(self, params: dict) -> str:
        folder = Path(params.get("path", ".")).resolve()
        if not folder.exists():
            return f"❌ Folder not found: {folder}"

        # Quick scan for context
        files = []
        for ext in SUPPORTED_EXTENSIONS:
            files.extend(folder.glob(f"*{ext}"))   # top-level only for README

        snippets = []
        for f in files[:8]:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")[:800]
                snippets.append(f"**{f.name}**:\n```\n{content}\n```")
            except Exception:
                continue

        context = "\n\n".join(snippets)
        prompt = (
            f"Generate a professional README.md for '{folder.name}'.\n\n"
            f"Include: description, features, installation, usage, project structure.\n\n"
            f"Code context:\n{context}"
        )

        readme = await self._ask_ollama(prompt)
        if not readme:
            return "❌ Failed to generate README — is Ollama running?"

        readme_path = folder / "README.md"
        # Don't overwrite existing README without warning
        if readme_path.exists():
            readme_path = folder / f"README_generated_{datetime.now().strftime('%Y%m%d')}.md"

        readme_path.write_text(readme, encoding="utf-8")
        return f"✅ README generated, sir.\n\n📄 {readme_path}\n\n{readme[:400]}..."

    async def _summarize_code(self, params: dict) -> str:
        path = Path(params.get("path", "")).resolve()
        if not path.exists():
            return f"❌ Not found: {path}"
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")[:3000]
        except Exception as e:
            return f"❌ Could not read: {e}"

        prompt = f"In 3-5 sentences, explain what this code does and its main purpose:\n\n{content}"
        summary = await self._ask_ollama(prompt)
        return f"📝 {path.name}:\n\n{summary}" if summary else "❌ Ollama unavailable."

    # ── Ollama ────────────────────────────────────────────────────────────────

    async def _ask_ollama(self, prompt: str) -> str | None:
        try:
            import ollama as ollama_lib
            loop = asyncio.get_event_loop()

            def _call():
                c = ollama_lib.Client(host=self._ollama_host)
                return c.chat(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": README_SYSTEM_PROMPT},
                        {"role": "user",   "content": prompt},
                    ],
                    options={"temperature": 0.3},
                    keep_alive="30m",
                )

            response = await asyncio.wait_for(loop.run_in_executor(None, _call), timeout=90.0)
            return response["message"]["content"].strip()
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.error(f"Auto-documenter Ollama error: {e}")
            return None
