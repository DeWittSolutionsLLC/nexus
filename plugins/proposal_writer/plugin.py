"""
Proposal Writer Plugin — JARVIS generates professional PDF proposals.

"Write a proposal for a $3k e-commerce site for Mike's Bakery"
→ Pulls in client/project data, drafts via Ollama, exports a PDF.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.proposal_writer")

PROPOSALS_DIR = Path.home() / "NexusProposals"


class ProposalWriterPlugin(BasePlugin):
    name = "proposal_writer"
    description = "Generate professional PDF project proposals from a description"
    icon = "📋"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._ollama_host = config.get("ollama_host", "http://localhost:11434")
        self._model = config.get("model", "llama3.1:8b")
        self._business_name = config.get("business_name", "Your Web Studio")
        self._your_name = config.get("your_name", "Developer")
        self._proposals: dict[str, dict] = {}
        PROPOSALS_DIR.mkdir(exist_ok=True)

    async def connect(self) -> bool:
        self._connected = True
        self._status_message = f"Ready — proposals saved to {PROPOSALS_DIR}"
        return True

    async def execute(self, action: str, params: dict) -> str:
        dispatch = {
            "write_proposal": self._write_proposal,
            "list_proposals": self._list_proposals,
            "open_proposal":  self._open_proposal,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"❌ Unknown action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "write_proposal", "description": "Generate a professional PDF proposal for a client project", "params": ["description", "client", "amount", "timeline"]},
            {"action": "list_proposals", "description": "List all generated proposals", "params": []},
            {"action": "open_proposal",  "description": "Open a proposal PDF", "params": ["name"]},
        ]

    # ── Actions ──────────────────────────────────────────────────────────────

    async def _write_proposal(self, params: dict) -> str:
        description = params.get("description", "").strip()
        client = params.get("client", "Client").strip()
        amount = params.get("amount", "")
        timeline = params.get("timeline", "4-6 weeks")

        if not description:
            return "❌ Please describe the project, sir."

        # Generate proposal content via Ollama
        content = await self._generate_proposal_content(description, client, amount, timeline)
        if not content:
            content = self._fallback_proposal(description, client, amount, timeline)

        # Try PDF export, fall back to text
        name = f"{client.replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}"
        pdf_result = await self._export_pdf(name, content, client, amount, timeline)

        self._proposals[name] = {
            "client": client, "description": description,
            "amount": amount, "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "path": str(PROPOSALS_DIR / f"{name}.pdf"),
        }

        return pdf_result

    async def _list_proposals(self, params: dict) -> str:
        # Also scan disk
        disk = list(PROPOSALS_DIR.glob("*.pdf")) + list(PROPOSALS_DIR.glob("*.txt"))
        if not self._proposals and not disk:
            return "📋 No proposals generated yet, sir.\n\nTry: 'write a proposal for a $2,500 portfolio site for Sarah's Photography'"
        lines = [f"📋 Proposals in {PROPOSALS_DIR}:\n"]
        for name, data in self._proposals.items():
            lines.append(f"  📄 {name}")
            lines.append(f"      Client: {data['client']}  |  Amount: {data.get('amount','—')}")
            lines.append(f"      Created: {data['created']}\n")
        for p in disk:
            if p.stem not in self._proposals:
                lines.append(f"  📄 {p.name}  [on disk]")
        return "\n".join(lines)

    async def _open_proposal(self, params: dict) -> str:
        import os
        name = params.get("name", "")
        data = self._proposals.get(name)
        if data:
            path = Path(data["path"])
        else:
            matches = list(PROPOSALS_DIR.glob(f"*{name}*"))
            path = matches[0] if matches else None
        if not path or not path.exists():
            return f"❌ Proposal '{name}' not found."
        try:
            os.startfile(str(path))
            return f"✅ Opening proposal: {path.name}"
        except Exception as e:
            return f"❌ Could not open: {e}\n  Path: {path}"

    # ── Generation ────────────────────────────────────────────────────────────

    async def _generate_proposal_content(self, description, client, amount, timeline) -> dict | None:
        prompt = f"""Write a professional web development proposal with these sections:
1. Executive Summary (2-3 sentences)
2. Project Scope (3-5 bullet points of deliverables)
3. Technical Approach (brief paragraph)
4. Timeline ({timeline})
5. Investment (${amount} breakdown if possible)
6. Next Steps

Project: {description}
Client: {client}
Budget: ${amount}

Return as JSON with keys: summary, scope (list), approach, timeline, investment, next_steps"""

        try:
            import ollama as ollama_lib
            loop = asyncio.get_event_loop()

            def _call():
                client_obj = ollama_lib.Client(host=self._ollama_host)
                return client_obj.chat(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.4},
                    keep_alive="30m",
                )

            response = await asyncio.wait_for(loop.run_in_executor(None, _call), timeout=60.0)
            text = response["message"]["content"].strip()

            # Try to extract JSON
            if "{" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                try:
                    return json.loads(text[start:end])
                except Exception:
                    pass
            return {"summary": text, "scope": [], "approach": "", "timeline": timeline, "investment": str(amount), "next_steps": "Contact us to proceed."}
        except Exception as e:
            logger.error(f"Proposal generation error: {e}")
            return None

    def _fallback_proposal(self, description, client, amount, timeline) -> dict:
        return {
            "summary": f"We propose to deliver {description} for {client}, completed to the highest professional standard.",
            "scope": ["Full design and development", "Responsive mobile layout", "Testing and QA", "Deployment and launch", "30-day post-launch support"],
            "approach": "Using modern web technologies and best practices to deliver a fast, secure, and scalable solution.",
            "timeline": timeline,
            "investment": f"${amount}" if amount else "To be discussed",
            "next_steps": "Review this proposal and contact us to schedule a kickoff call.",
        }

    async def _export_pdf(self, name: str, content: dict, client: str, amount: str, timeline: str) -> str:
        path = PROPOSALS_DIR / f"{name}.pdf"
        txt_path = PROPOSALS_DIR / f"{name}.txt"

        # Try fpdf2 first
        try:
            from fpdf import FPDF

            pdf = FPDF()
            pdf.set_margins(20, 20, 20)
            pdf.add_page()

            # Header
            pdf.set_font("Helvetica", "B", 22)
            pdf.set_text_color(0, 150, 200)
            pdf.cell(0, 12, "PROJECT PROPOSAL", ln=True, align="C")
            pdf.set_font("Helvetica", "", 11)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(0, 8, f"{self._business_name}  ·  {datetime.now().strftime('%B %d, %Y')}", ln=True, align="C")
            pdf.ln(8)

            # Client / amount bar
            pdf.set_fill_color(240, 248, 255)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(90, 10, f"Prepared for:  {client}", border=0, fill=True)
            pdf.cell(80, 10, f"Investment:  ${amount}", border=0, fill=True, align="R")
            pdf.ln(14)

            def section(title, body):
                pdf.set_font("Helvetica", "B", 12)
                pdf.set_text_color(0, 100, 180)
                pdf.cell(0, 8, title, ln=True)
                pdf.set_draw_color(0, 150, 200)
                pdf.line(20, pdf.get_y(), 190, pdf.get_y())
                pdf.ln(3)
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(50, 50, 50)
                if isinstance(body, list):
                    for item in body:
                        pdf.cell(6, 7, "•", ln=False)
                        pdf.multi_cell(0, 7, str(item))
                else:
                    pdf.multi_cell(0, 7, str(body))
                pdf.ln(4)

            section("Executive Summary", content.get("summary", ""))
            section("Project Scope", content.get("scope", []))
            section("Technical Approach", content.get("approach", ""))
            section("Timeline", content.get("timeline", timeline))
            section("Investment", content.get("investment", f"${amount}"))
            section("Next Steps", content.get("next_steps", ""))

            # Footer
            pdf.set_y(-25)
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(150, 150, 150)
            pdf.cell(0, 5, f"{self._business_name}  —  This proposal is valid for 30 days", align="C", ln=True)

            pdf.output(str(path))
            return (
                f"✅ Proposal for '{client}' generated, sir.\n\n"
                f"📄 PDF: {path}\n\n"
                f"Say 'open proposal {name}' to view it."
            )

        except ImportError:
            # Fall back to plain text
            lines = [
                f"PROJECT PROPOSAL", f"{'='*50}",
                f"Prepared for: {client}",
                f"Date: {datetime.now().strftime('%B %d, %Y')}",
                f"Investment: ${amount}",
                f"Timeline: {timeline}",
                "", "EXECUTIVE SUMMARY", "-"*30,
                content.get("summary", ""),
                "", "PROJECT SCOPE", "-"*30,
            ]
            for item in content.get("scope", []):
                lines.append(f"• {item}")
            lines += [
                "", "APPROACH", "-"*30, content.get("approach", ""),
                "", "INVESTMENT", "-"*30, content.get("investment", f"${amount}"),
                "", "NEXT STEPS", "-"*30, content.get("next_steps", ""),
            ]
            txt_path.write_text("\n".join(lines), encoding="utf-8")
            return (
                f"✅ Proposal written (text format — install fpdf2 for PDF):\n\n"
                f"📄 {txt_path}\n\n"
                f"Install PDF support: pip install fpdf2"
            )
