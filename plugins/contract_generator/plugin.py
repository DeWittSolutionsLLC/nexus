"""
Contract Generator Plugin — Generate professional contract documents via Ollama.
Exports to PDF (fpdf2) or plain text. Stores in ~/NexusScripts/contracts/.
"""

import json
import logging
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from core.plugin_manager import BasePlugin
import requests

logger = logging.getLogger("nexus.plugins.contract_generator")

CONTRACTS_DIR = Path.home() / "NexusScripts" / "contracts"

CONTRACT_TYPES = ["freelance", "nda", "service_agreement", "employment", "consulting"]

try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False
    logger.info("fpdf2 not available — contracts will be saved as .txt files")


class ContractGeneratorPlugin(BasePlugin):
    name = "contract_generator"
    description = "Generate professional contracts via AI — freelance, NDA, service, employment, consulting"
    icon = "📝"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)

    async def connect(self) -> bool:
        CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
        self._connected = True
        count = len(list(CONTRACTS_DIR.glob("*")))
        fmt = "PDF" if HAS_FPDF else "TXT"
        self._status_message = f"{count} contracts on file | Output: {fmt}"
        return True

    async def execute(self, action: str, params: dict) -> str:
        handler = {
            "generate_contract": self._generate_contract,
            "list_contracts":    self._list_contracts,
            "get_contract":      self._get_contract,
            "delete_contract":   self._delete_contract,
        }.get(action)
        if not handler:
            return f"Unknown action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "generate_contract", "description": "Generate a professional contract document using AI",      "params": ["type", "client_name", "your_name", "project_description", "amount", "currency", "duration"]},
            {"action": "list_contracts",    "description": "List all generated contracts",                            "params": []},
            {"action": "get_contract",      "description": "View the text content of a contract",                    "params": ["filename"]},
            {"action": "delete_contract",   "description": "Delete a contract file",                                 "params": ["filename"]},
        ]

    def _build_prompt(self, contract_type: str, client_name: str, your_name: str,
                      project_description: str, amount: float, currency: str, duration: str) -> str:
        today = date.today().strftime("%B %d, %Y")
        type_labels = {
            "freelance":        "Freelance Services Agreement",
            "nda":              "Non-Disclosure Agreement (NDA)",
            "service_agreement":"Service Agreement",
            "employment":       "Employment Contract",
            "consulting":       "Consulting Agreement",
        }
        label = type_labels.get(contract_type, "Professional Agreement")

        return (
            f"Write a complete, professional {label} with the following details:\n\n"
            f"- Date: {today}\n"
            f"- Service Provider / Your Name: {your_name}\n"
            f"- Client Name: {client_name}\n"
            f"- Project / Scope of Work: {project_description}\n"
            f"- Compensation: {currency} {amount:.2f}\n"
            f"- Duration / Timeline: {duration}\n\n"
            f"Include all standard clauses: parties, scope of work, payment terms, "
            f"confidentiality, intellectual property, termination, limitation of liability, "
            f"governing law, and signature blocks. Write in formal legal language. "
            f"Do not add any commentary — output only the contract text."
        )

    def _call_ollama(self, prompt: str) -> str:
        try:
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "llama3.2:3b", "prompt": prompt, "stream": False},
                timeout=90
            )
            result = resp.json().get("response", "")
            if not result:
                return "AI returned an empty response. Please try again."
            return result
        except requests.exceptions.ConnectionError:
            return ""
        except Exception as e:
            logger.error(f"Ollama call failed: {e}")
            return ""

    def _save_as_pdf(self, filename: str, title: str, contract_text: str) -> Path:
        pdf = FPDF()
        pdf.set_margins(20, 20, 20)
        pdf.add_page()

        # Header
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, title, ln=True, align="C")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"Generated: {date.today().isoformat()}", ln=True, align="C")
        pdf.ln(6)

        # Divider
        pdf.set_draw_color(100, 100, 100)
        pdf.line(20, pdf.get_y(), 190, pdf.get_y())
        pdf.ln(6)

        # Body
        pdf.set_font("Helvetica", "", 11)
        for paragraph in contract_text.split("\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                pdf.ln(4)
                continue
            if re.match(r'^[A-Z][A-Z\s]+$', paragraph) or paragraph.startswith("##"):
                pdf.set_font("Helvetica", "B", 12)
                pdf.multi_cell(0, 7, paragraph.replace("##", "").strip())
                pdf.set_font("Helvetica", "", 11)
            else:
                pdf.multi_cell(0, 6, paragraph)

        # Signature block
        pdf.ln(10)
        pdf.line(20, pdf.get_y(), 190, pdf.get_y())
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(90, 7, "Service Provider Signature:", ln=False)
        pdf.cell(90, 7, "Client Signature:", ln=True)
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(90, 14, "_______________________", ln=False)
        pdf.cell(90, 14, "_______________________", ln=True)
        pdf.cell(90, 7, "Date: ________________", ln=False)
        pdf.cell(90, 7, "Date: ________________", ln=True)

        out_path = CONTRACTS_DIR / filename
        pdf.output(str(out_path))
        return out_path

    def _save_as_txt(self, filename: str, title: str, contract_text: str) -> Path:
        out_path = CONTRACTS_DIR / filename
        header = (
            f"{'='*70}\n"
            f"  {title}\n"
            f"  Generated: {date.today().isoformat()}\n"
            f"{'='*70}\n\n"
        )
        sig_block = (
            f"\n\n{'─'*70}\n"
            f"SIGNATURES\n\n"
            f"Service Provider: _______________________  Date: __________\n\n"
            f"Client:           _______________________  Date: __________\n"
        )
        out_path.write_text(header + contract_text + sig_block, encoding="utf-8")
        return out_path

    async def _generate_contract(self, params: dict) -> str:
        contract_type = params.get("type", "freelance").lower().replace(" ", "_")
        if contract_type not in CONTRACT_TYPES:
            return f"Unknown contract type '{contract_type}'. Available: {', '.join(CONTRACT_TYPES)}"

        client_name = params.get("client_name", "").strip()
        your_name = params.get("your_name", "").strip()
        project_description = params.get("project_description", "").strip()
        if not client_name or not your_name or not project_description:
            return "Please provide client_name, your_name, and project_description."

        try:
            amount = float(params.get("amount", 0))
        except (ValueError, TypeError):
            amount = 0.0
        currency = params.get("currency", "USD").strip().upper()
        duration = params.get("duration", "To be agreed").strip()

        type_labels = {
            "freelance": "Freelance Services Agreement", "nda": "Non-Disclosure Agreement",
            "service_agreement": "Service Agreement", "employment": "Employment Contract",
            "consulting": "Consulting Agreement",
        }
        title = type_labels.get(contract_type, "Professional Agreement")

        prompt = self._build_prompt(contract_type, client_name, your_name, project_description, amount, currency, duration)
        contract_text = self._call_ollama(prompt)

        if not contract_text:
            contract_text = (
                f"This {title} is entered into as of {date.today().strftime('%B %d, %Y')} "
                f"between {your_name} ('Service Provider') and {client_name} ('Client').\n\n"
                f"SCOPE OF WORK\nService Provider agrees to: {project_description}\n\n"
                f"COMPENSATION\nClient agrees to pay {currency} {amount:.2f} for the services described above.\n\n"
                f"DURATION\n{duration}\n\n"
                f"CONFIDENTIALITY\nBoth parties agree to maintain confidentiality of all proprietary information.\n\n"
                f"TERMINATION\nEither party may terminate this agreement with 14 days written notice.\n\n"
                f"GOVERNING LAW\nThis agreement shall be governed by applicable law.\n\n"
                f"[Note: AI generation unavailable — this is a basic template. Please review and customize before use.]"
            )

        uid = str(uuid.uuid4())[:8]
        safe_client = re.sub(r'[^a-zA-Z0-9]', '_', client_name)[:20]
        ext = ".pdf" if HAS_FPDF else ".txt"
        filename = f"{contract_type}_{safe_client}_{uid}{ext}"

        try:
            if HAS_FPDF:
                out_path = self._save_as_pdf(filename, title, contract_text)
            else:
                out_path = self._save_as_txt(filename, title, contract_text)
        except Exception as e:
            logger.error(f"Failed to save contract: {e}")
            return f"Contract generated but failed to save: {e}"

        word_count = len(contract_text.split())
        return (
            f"Contract generated and saved.\n\n"
            f"  Title:    {title}\n"
            f"  Client:   {client_name}\n"
            f"  Provider: {your_name}\n"
            f"  Amount:   {currency} {amount:.2f}\n"
            f"  Duration: {duration}\n"
            f"  File:     {filename}\n"
            f"  Format:   {'PDF' if HAS_FPDF else 'TXT'}\n"
            f"  Length:   ~{word_count} words\n"
            f"  Path:     {out_path}"
        )

    async def _list_contracts(self, params: dict) -> str:
        files = sorted(CONTRACTS_DIR.glob("*"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            return "No contracts on file yet. Use generate_contract to create one."
        lines = [f"CONTRACTS  ({len(files)} files)", "─" * 60]
        for f in files:
            size_kb = f.stat().st_size / 1024
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            lines.append(f"  {f.name:<45}  {size_kb:>5.1f} KB  {mtime}")
        return "\n".join(lines)

    async def _get_contract(self, params: dict) -> str:
        filename = params.get("filename", "").strip()
        if not filename:
            return "Please provide a filename."
        path = CONTRACTS_DIR / filename
        if not path.exists():
            return f"Contract '{filename}' not found."
        if path.suffix == ".pdf":
            return f"Contract '{filename}' is a PDF file at:\n{path}\n\nOpen it with a PDF viewer to read."
        try:
            text = path.read_text(encoding="utf-8")
            if len(text) > 3000:
                return text[:3000] + f"\n\n[... truncated — full file at {path}]"
            return text
        except Exception as e:
            return f"Could not read contract: {e}"

    async def _delete_contract(self, params: dict) -> str:
        filename = params.get("filename", "").strip()
        if not filename:
            return "Please provide a filename."
        path = CONTRACTS_DIR / filename
        if not path.exists():
            return f"Contract '{filename}' not found."
        path.unlink()
        return f"Contract '{filename}' deleted."
