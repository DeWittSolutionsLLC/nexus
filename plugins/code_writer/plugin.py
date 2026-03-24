"""
Code Writer Plugin — JARVIS writes, edits, and runs code autonomously.

"Write a Python script that renames all photos by date" →
  • Ollama generates the code
  • Plugin saves it to ~/NexusScripts/
  • Optionally runs it and returns output
"""

import asyncio
import logging
import os
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path

from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.code_writer")

SCRIPTS_DIR = Path.home() / "NexusScripts"

CODE_SYSTEM_PROMPT = """You are an expert programmer assistant for JARVIS. Write clean, working code.

RULES:
- Output ONLY the code — no markdown fences, no explanation before/after
- Include a brief comment at the top describing what the script does
- Handle errors gracefully with try/except
- For file operations, always confirm before deleting/overwriting
- Use pathlib for file paths, not os.path
- Scripts should print clear status messages as they run
"""


class CodeWriterPlugin(BasePlugin):
    name = "code_writer"
    description = "Write, edit, and run code scripts autonomously via AI"
    icon = "💻"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._ollama_host = config.get("ollama_host", "http://localhost:11434")
        self._model = config.get("model", "llama3.1:8b")
        self._scripts: dict[str, dict] = {}
        SCRIPTS_DIR.mkdir(exist_ok=True)

    async def connect(self) -> bool:
        self._connected = True
        self._status_message = f"Ready — scripts in {SCRIPTS_DIR}"
        return True

    async def execute(self, action: str, params: dict) -> str:
        dispatch = {
            "write_script":  self._write_script,
            "run_script":    self._run_script,
            "write_and_run": self._write_and_run,
            "edit_script":   self._edit_script,
            "show_script":   self._show_script,
            "list_scripts":  self._list_scripts,
            "delete_script": self._delete_script,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"❌ Unknown action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "write_script",  "description": "Write a new script from a natural language description", "params": ["description", "name", "language"]},
            {"action": "run_script",    "description": "Run a previously written script", "params": ["name", "args"]},
            {"action": "write_and_run", "description": "Write a script and immediately run it", "params": ["description", "name", "language"]},
            {"action": "edit_script",   "description": "Edit an existing script based on instructions", "params": ["name", "instruction"]},
            {"action": "show_script",   "description": "Show the contents of a script", "params": ["name"]},
            {"action": "list_scripts",  "description": "List all saved scripts", "params": []},
            {"action": "delete_script", "description": "Delete a script", "params": ["name"]},
        ]

    # ── Write ────────────────────────────────────────────────────────────────

    async def _write_script(self, params: dict) -> str:
        description = params.get("description", "").strip()
        name = params.get("name") or f"script_{datetime.now().strftime('%H%M%S')}"
        lang = params.get("language", "python").lower()
        if not description:
            return "❌ Please provide a description of what the script should do."

        code = await self._generate_code(description, lang)
        if not code:
            return "❌ Failed to generate code — is Ollama running?"

        ext = {"python": ".py", "bash": ".sh", "powershell": ".ps1", "javascript": ".js"}.get(lang, ".py")
        safe_name = "".join(c if (c.isalnum() or c in "-_") else "_" for c in name)
        path = SCRIPTS_DIR / f"{safe_name}{ext}"
        path.write_text(code, encoding="utf-8")

        self._scripts[name] = {"path": str(path), "lang": lang, "description": description, "created": datetime.now().strftime("%Y-%m-%d %H:%M")}
        return (
            f"✅ Script '{name}' written, sir.\n\n"
            f"📄 {path}\n\n"
            f"```{lang}\n{code[:800]}{'...' if len(code) > 800 else ''}\n```\n\n"
            f"Say 'run {name}' to execute it."
        )

    async def _write_and_run(self, params: dict) -> str:
        write_result = await self._write_script(params)
        if "❌" in write_result:
            return write_result
        name = params.get("name") or "script_" + datetime.now().strftime("%H%M%S")
        # Find the last written script name
        actual_name = name if name in self._scripts else (list(self._scripts.keys())[-1] if self._scripts else None)
        if not actual_name:
            return write_result + "\n\n❌ Could not locate script to run."
        run_result = await self._run_script({"name": actual_name})
        return write_result + "\n\n" + run_result

    async def _edit_script(self, params: dict) -> str:
        name = params.get("name", "")
        instruction = params.get("instruction", "").strip()
        if not name or name not in self._scripts:
            return f"❌ Script '{name}' not found. Say 'list scripts' to see what's available."
        if not instruction:
            return "❌ Please provide editing instructions."

        path = Path(self._scripts[name]["path"])
        original = path.read_text(encoding="utf-8")
        lang = self._scripts[name]["lang"]

        prompt = f"Edit this {lang} script according to these instructions: {instruction}\n\nOriginal script:\n{original}\n\nReturn ONLY the complete updated script."
        updated = await self._generate_code(prompt, lang, raw=True)
        if not updated:
            return "❌ Failed to edit script — is Ollama running?"

        path.write_text(updated, encoding="utf-8")
        return f"✅ Script '{name}' updated, sir.\n\n```{lang}\n{updated[:600]}{'...' if len(updated) > 600 else ''}\n```"

    # ── Run ──────────────────────────────────────────────────────────────────

    async def _run_script(self, params: dict) -> str:
        name = params.get("name", "")
        args = params.get("args", "")

        # Try to find by name in registry, then fall back to direct path search
        script_data = self._scripts.get(name)
        if not script_data:
            matches = list(SCRIPTS_DIR.glob(f"{name}*"))
            if matches:
                path = matches[0]
                lang = "python" if path.suffix == ".py" else "bash"
                script_data = {"path": str(path), "lang": lang}
            else:
                return f"❌ Script '{name}' not found. Say 'list scripts' to see available scripts."

        path = Path(script_data["path"])
        lang = script_data.get("lang", "python")

        if not path.exists():
            return f"❌ Script file not found at {path}"

        cmd = self._build_run_command(path, lang, args)

        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: subprocess.run(
                    cmd, capture_output=True, text=True, timeout=30, cwd=str(SCRIPTS_DIR)
                )),
                timeout=35.0,
            )
            output = result.stdout.strip()
            errors = result.stderr.strip()
            rc = result.returncode

            lines = []
            lines.append(f"{'✅' if rc == 0 else '❌'} Script '{name}' exited with code {rc}\n")
            if output:
                lines.append(f"Output:\n{output[:2000]}{'...' if len(output) > 2000 else ''}")
            if errors:
                lines.append(f"Errors:\n{errors[:500]}")
            return "\n".join(lines)

        except asyncio.TimeoutError:
            return f"⚠️ Script '{name}' timed out after 30 seconds."
        except Exception as e:
            return f"❌ Failed to run script: {e}"

    def _build_run_command(self, path: Path, lang: str, args: str) -> list:
        base = {
            "python":     [sys.executable, str(path)],
            "bash":       ["bash", str(path)],
            "powershell": ["powershell", "-File", str(path)],
            "javascript": ["node", str(path)],
        }.get(lang, [sys.executable, str(path)])
        if args:
            base += args.split()
        return base

    # ── Utilities ────────────────────────────────────────────────────────────

    async def _show_script(self, params: dict) -> str:
        name = params.get("name", "")
        data = self._scripts.get(name)
        if not data:
            return f"❌ Script '{name}' not found."
        path = Path(data["path"])
        if not path.exists():
            return f"❌ File missing: {path}"
        code = path.read_text(encoding="utf-8")
        return f"📄 {name} ({data['lang']}):\n\n```{data['lang']}\n{code}\n```"

    async def _list_scripts(self, params: dict) -> str:
        # Also scan disk for any scripts not in registry
        disk_scripts = list(SCRIPTS_DIR.glob("*.*"))
        if not disk_scripts and not self._scripts:
            return (
                "💻 No scripts written yet, sir.\n\n"
                "Try: 'write a script that backs up my Desktop to Documents'"
            )
        lines = [f"💻 Scripts in {SCRIPTS_DIR}:\n"]
        seen = set()
        for name, data in self._scripts.items():
            seen.add(data["path"])
            lines.append(f"  📄 {name}  [{data['lang']}]")
            lines.append(f"      {data['description'][:60]}")
            lines.append(f"      {data['created']}\n")
        for p in disk_scripts:
            if str(p) not in seen:
                lines.append(f"  📄 {p.name}  [unregistered]")
        return "\n".join(lines)

    async def _delete_script(self, params: dict) -> str:
        name = params.get("name", "")
        data = self._scripts.get(name)
        if not data:
            return f"❌ Script '{name}' not found."
        path = Path(data["path"])
        if path.exists():
            path.unlink()
        del self._scripts[name]
        return f"🗑️ Script '{name}' deleted."

    # ── Ollama code generation ────────────────────────────────────────────────

    async def _generate_code(self, description: str, lang: str = "python", raw: bool = False) -> str | None:
        try:
            import ollama as ollama_lib
            loop = asyncio.get_event_loop()

            def _call():
                client = ollama_lib.Client(host=self._ollama_host)
                user_msg = description if raw else f"Write a {lang} script that: {description}"
                return client.chat(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": CODE_SYSTEM_PROMPT},
                        {"role": "user",   "content": user_msg},
                    ],
                    options={"temperature": 0.2},
                    keep_alive="30m",
                )

            response = await asyncio.wait_for(loop.run_in_executor(None, _call), timeout=60.0)
            code = response["message"]["content"].strip()
            # Strip markdown fences
            if "```" in code:
                lines = code.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                code = "\n".join(lines).strip()
            return code
        except Exception as e:
            logger.error(f"Code generation error: {e}")
            return None
