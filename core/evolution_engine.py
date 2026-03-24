"""
Evolution Engine — Nexus self-expansion and self-optimisation module.

Features:
  1. Autonomous plugin creation  — research, generate, validate, hot-load
  2. Recursive code reflection   — AI-powered suggestions + user-confirmed refactors

Safety protocol (enforced on every code write):
  - Generated / modified code is always saved to staging/ first
  - A `python -m py_compile` check must pass before promotion
  - Originals are backed up to staging/ before any in-place update
"""

import asyncio
import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import requests

logger = logging.getLogger("nexus.evolution")

OLLAMA_URL   = "http://localhost:11434/api/generate"
STAGING_DIR  = Path("staging")
PLUGINS_DIR  = Path("plugins")
CORE_DIR     = Path("core")

# ── Prompt templates ──────────────────────────────────────────────────────────

_PLUGIN_PROMPT = """\
You are writing a plugin for Nexus, a fully-local Python AI assistant.
Output ONLY valid Python code — no markdown fences, no commentary outside code.

Requirements:
1. from core.plugin_manager import BasePlugin
2. ONE class named {class_name}Plugin(BasePlugin)
3. Class attributes: name = "{plugin_name}", description = "...", icon = "..."
4. async connect(self) -> bool
5. async execute(self, action: str, params: dict) -> str   ← dispatch with try/except
6. get_capabilities(self) -> list[dict]
7. Use only stdlib + common pip packages (requests, pathlib, json, etc.)

Plugin name   : {plugin_name}
Purpose       : {description}
Research notes: {research}

Write the complete plugin.py now:
"""

_REFLECT_SYSTEM = """\
You are a senior Python engineer performing a targeted performance and quality review.
Analyse the provided source and identify the top 1-3 *concrete*, *safe* improvements.
For EACH improvement provide:
  - A one-sentence description of the issue
  - The exact old snippet (verbatim, ≤ 10 lines)
  - The exact replacement snippet

Respond ONLY with this JSON (no text outside it):
{
  "file": "<filename>",
  "improvements": [
    {"issue": "...", "old": "...", "new": "..."}
  ]
}
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def _ollama(prompt: str, system: str = "", model: str = "llama3.2:3b",
            host: str = "http://localhost:11434", timeout: int = 180) -> str:
    url = host.rstrip("/") + "/api/generate"
    payload: dict = {"model": model, "prompt": prompt, "stream": False}
    if system:
        payload["system"] = system
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        return f"[Ollama error: {e}]"


def _strip_fences(code: str) -> str:
    lines = code.split("\n")
    return "\n".join(l for l in lines if not l.strip().startswith("```")).strip()


def _compile_check(path: Path) -> tuple[bool, str]:
    """Return (passed, error_message). Runs python -m py_compile."""
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode == 0:
        return True, ""
    return False, (result.stderr or result.stdout).strip()


def _to_snake_case(description: str) -> str:
    """Derive a safe snake_case plugin name from a natural-language description."""
    import re
    words = re.findall(r"[a-zA-Z]+", description.lower())
    stop = {"a", "an", "the", "for", "that", "which", "with", "and",
            "or", "to", "of", "in", "plugin", "me", "build", "create",
            "make", "write", "new", "i", "need", "want"}
    words = [w for w in words if w not in stop][:4]
    return "_".join(words) if words else "custom_plugin"


# ── Evolution Engine ──────────────────────────────────────────────────────────

class EvolutionEngine:
    """
    Core self-evolution logic.  Consumed by the evolution_engine plugin
    and optionally called directly from the Observer thread.
    """

    def __init__(self, plugin_manager, ai_config: dict):
        self.plugin_manager = plugin_manager
        self._model = ai_config.get("model", "llama3.2:3b")
        self._host  = ai_config.get("ollama_host", "http://localhost:11434")
        self._pending_refactors: list = []
        STAGING_DIR.mkdir(exist_ok=True)

    # ── Feature 1: Autonomous Plugin Creation ─────────────────────────────────

    async def create_plugin(self, description: str) -> str:
        """
        Research → generate → validate → hot-load a brand-new plugin.
        Returns a multi-line status string for the UI.
        """
        log: list[str] = []

        def note(msg: str):
            logger.info(msg)
            log.append(msg)

        note(f"◆ Autonomous Plugin Architect engaged.\n  Requirement: {description}")

        # Derive name
        plugin_name = _to_snake_case(description)
        class_name  = "".join(w.capitalize() for w in plugin_name.split("_"))
        note(f"  Proposed identifier: '{plugin_name}'")

        # Research via research_agent (best-effort)
        research = "No external research available."
        rp = self.plugin_manager.get_plugin("research_agent")
        if rp and rp.is_connected:
            note("  Consulting research_agent for relevant libraries...")
            try:
                research = await rp.execute("search", {"query": f"Python library for {description}"})
                research = research[:600]
            except Exception as ex:
                research = f"Research unavailable: {ex}"

        note("  Research complete. Drafting plugin source via Ollama...")

        # Generate code
        prompt = _PLUGIN_PROMPT.format(
            class_name=class_name,
            plugin_name=plugin_name,
            description=description,
            research=research,
        )
        code = _ollama(prompt, model=self._model, host=self._host, timeout=180)
        code = _strip_fences(code)

        if "BasePlugin" not in code or "async def execute" not in code:
            note(
                "  I'm afraid the generated code didn't meet the structural requirements, sir.\n"
                "  Please try a more specific description — the model may need clearer intent."
            )
            return "\n".join(log)

        # Save to staging/
        staging_dir = STAGING_DIR / plugin_name
        staging_dir.mkdir(parents=True, exist_ok=True)
        staging_file = staging_dir / "plugin.py"
        (staging_dir / "__init__.py").write_text("", encoding="utf-8")
        staging_file.write_text(code, encoding="utf-8")
        note(f"  Saved to staging/{plugin_name}/plugin.py — running syntax validation...")

        # Safety check
        ok, err = _compile_check(staging_file)
        if not ok:
            note(
                f"  Most regrettably — the generated code contains a syntax error:\n"
                f"    {err[:200]}\n"
                f"  The file remains in staging/ for your review. No active systems were modified."
            )
            return "\n".join(log)

        note("  Syntax check passed. Promoting to plugins/ directory...")

        # Promote
        target = PLUGINS_DIR / plugin_name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(str(staging_dir), str(target))

        # Hot-load
        loaded = self.plugin_manager.hot_load_plugin(plugin_name)
        if loaded:
            note(
                f"  '{plugin_name}' is now live, sir. I've taken the liberty of registering\n"
                f"  it with all active systems. You may address it immediately."
            )
        else:
            note(
                f"  The plugin is in place, sir, but the hot-loader encountered an issue.\n"
                f"  A restart of Nexus will activate '{plugin_name}' properly."
            )

        return "\n".join(log)

    # ── Feature 2: Recursive Code Reflection ─────────────────────────────────

    async def reflect_on_code(self) -> str:
        """
        Read core/ source files, ask Ollama for optimisation suggestions,
        store results as pending refactors and return a summary for the user.
        """
        core_files = [f for f in CORE_DIR.glob("*.py") if f.stat().st_size > 200]
        if not core_files:
            return "No source files found in core/ to reflect upon, sir."

        log: list[str] = [
            f"◆ Self-Reflection Protocol — analysing {len(core_files)} source file(s).\n"
            "  Even JARVIS benefits from the occasional introspective pause...\n"
        ]

        self._pending_refactors = []

        for fpath in core_files[:4]:  # cap at 4 files per session
            try:
                source = fpath.read_text(encoding="utf-8")[:4000]
            except Exception:
                continue

            raw = _ollama(
                f"File: {fpath.name}\n\n{source}",
                system=_REFLECT_SYSTEM,
                model=self._model,
                host=self._host,
                timeout=120,
            )

            try:
                start, end = raw.find("{"), raw.rfind("}") + 1
                if start != -1 and end > start:
                    report = json.loads(raw[start:end])
                    if report.get("improvements"):
                        self._pending_refactors.append((fpath, report))
            except Exception:
                pass

        if not self._pending_refactors:
            return (
                "After careful introspection, I find the codebase rather satisfactory, sir. "
                "No significant optimisations identified at this time."
            )

        for fpath, report in self._pending_refactors:
            log.append(f"  File: {fpath.name}")
            for i, imp in enumerate(report["improvements"], 1):
                log.append(f"    {i}. {imp['issue']}")
            log.append("")

        log.append(
            "To apply these refactors, say: 'Nexus, apply the refactors'\n"
            "Or: 'Nexus, skip the refactors' to leave things as they are."
        )
        return "\n".join(log)

    async def apply_pending_refactors(self) -> str:
        """Apply the last set of pending refactors after user confirmation."""
        if not self._pending_refactors:
            return "No pending refactors in the queue, sir."

        applied, skipped = 0, 0
        for fpath, report in self._pending_refactors:
            try:
                source = fpath.read_text(encoding="utf-8")
            except Exception:
                skipped += 1
                continue

            modified = source
            for imp in report.get("improvements", []):
                old, new = imp.get("old", ""), imp.get("new", "")
                if old and new and old in modified:
                    modified = modified.replace(old, new, 1)

            if modified == source:
                skipped += 1
                continue

            # Stage the modified version
            staging_copy = STAGING_DIR / fpath.name
            staging_copy.write_text(modified, encoding="utf-8")
            ok, err = _compile_check(staging_copy)
            if not ok:
                skipped += 1
                logger.warning(f"Refactor skipped for {fpath.name}: {err[:80]}")
                continue

            # Backup then promote
            backup = STAGING_DIR / f"{fpath.stem}_backup_{datetime.now().strftime('%H%M%S')}.py"
            shutil.copy(fpath, backup)
            fpath.write_text(modified, encoding="utf-8")
            applied += 1

        self._pending_refactors = []
        return (
            f"◆ Refactoring complete, sir. {applied} file(s) updated, "
            f"{skipped} unchanged. Originals backed up to staging/."
        )

    def skip_pending_refactors(self) -> str:
        self._pending_refactors = []
        return "Understood, sir. Pending refactors discarded — the codebase remains untouched."
