"""
Email Composer Plugin — AI-powered email composition via Ollama.
Optional SMTP sending. Drafts saved locally in ~/NexusScripts/email_drafts.json.
"""

import json
import logging
import smtplib
import uuid
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from core.plugin_manager import BasePlugin
import requests

logger = logging.getLogger("nexus.plugins.email_composer")

DRAFTS_FILE = Path.home() / "NexusScripts" / "email_drafts.json"

TONE_HINTS = {
    "professional": "professional and business-appropriate",
    "friendly":     "warm, friendly, and conversational",
    "formal":       "very formal, polite, and structured",
    "urgent":       "urgent and direct, conveying time-sensitivity",
}


class EmailComposerPlugin(BasePlugin):
    name = "email_composer"
    description = "AI-powered email composition and sending — drafts, replies, tone adjustment"
    icon = "✉"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.drafts: list[dict] = []
        self._load()

    def _load(self):
        if DRAFTS_FILE.exists():
            try:
                self.drafts = json.loads(DRAFTS_FILE.read_text(encoding="utf-8"))
                if not isinstance(self.drafts, list):
                    self.drafts = []
            except Exception as e:
                logger.warning(f"Could not load drafts: {e}")
                self.drafts = []

    def _save(self):
        DRAFTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        DRAFTS_FILE.write_text(
            json.dumps(self.drafts, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )

    async def connect(self) -> bool:
        self._connected = True
        smtp_configured = bool(self.config.get("smtp_host"))
        smtp_note = "SMTP configured" if smtp_configured else "No SMTP (compose only)"
        self._status_message = f"{len(self.drafts)} drafts | {smtp_note}"
        return True

    async def execute(self, action: str, params: dict) -> str:
        handler = {
            "compose":        self._compose,
            "send_email":     self._send_email,
            "list_drafts":    self._list_drafts,
            "get_draft":      self._get_draft,
            "delete_draft":   self._delete_draft,
            "improve_email":  self._improve_email,
            "reply_template": self._reply_template,
        }.get(action)
        if not handler:
            return f"Unknown action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "compose",        "description": "AI-compose a professional email from key points",         "params": ["recipient", "subject", "key_points", "tone"]},
            {"action": "send_email",     "description": "Send an email via SMTP (requires SMTP config)",           "params": ["to", "subject", "body"]},
            {"action": "list_drafts",    "description": "List all saved email drafts",                             "params": []},
            {"action": "get_draft",      "description": "View a specific email draft",                             "params": ["id"]},
            {"action": "delete_draft",   "description": "Delete a draft by ID",                                    "params": ["id"]},
            {"action": "improve_email",  "description": "AI-improve an existing email with specific instruction",  "params": ["text", "instruction"]},
            {"action": "reply_template", "description": "Generate a reply to an existing email",                   "params": ["original_email", "reply_intent"]},
        ]

    def _call_ollama(self, prompt: str) -> str:
        try:
            resp = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": "llama3.2:3b", "prompt": prompt, "stream": False},
                timeout=60
            )
            result = resp.json().get("response", "")
            return result.strip()
        except requests.exceptions.ConnectionError:
            return ""
        except Exception as e:
            logger.error(f"Ollama call failed: {e}")
            return ""

    def _save_draft(self, recipient: str, subject: str, body: str, tone: str = "professional") -> dict:
        draft = {
            "id":        str(uuid.uuid4())[:8],
            "recipient": recipient,
            "subject":   subject,
            "body":      body,
            "tone":      tone,
            "created":   datetime.now().isoformat(),
        }
        self.drafts.append(draft)
        self._save()
        return draft

    async def _compose(self, params: dict) -> str:
        recipient = params.get("recipient", "").strip()
        subject = params.get("subject", "").strip()
        key_points = params.get("key_points", "").strip()
        tone = params.get("tone", "professional").lower()

        if not recipient or not subject or not key_points:
            return "Please provide recipient, subject, and key_points."

        tone_desc = TONE_HINTS.get(tone, TONE_HINTS["professional"])
        prompt = (
            f"Write a complete, {tone_desc} email with the following details:\n\n"
            f"- Recipient: {recipient}\n"
            f"- Subject: {subject}\n"
            f"- Key points to cover: {key_points}\n\n"
            f"Write only the email body — start with a greeting, include all key points naturally, "
            f"and end with an appropriate sign-off. Do not include the subject line or 'To:' header."
        )

        body = self._call_ollama(prompt)
        if not body:
            body = (
                f"Dear {recipient},\n\n"
                f"I hope this message finds you well.\n\n"
                f"{key_points}\n\n"
                f"Please don't hesitate to reach out if you have any questions.\n\n"
                f"Best regards"
                f"\n\n[Note: AI unavailable — this is a basic template.]"
            )

        draft = self._save_draft(recipient, subject, body, tone)
        return (
            f"Email composed and saved as draft.\n\n"
            f"  Draft ID:  {draft['id']}\n"
            f"  To:        {recipient}\n"
            f"  Subject:   {subject}\n"
            f"  Tone:      {tone}\n\n"
            f"{'─'*50}\n"
            f"{body}\n"
            f"{'─'*50}\n\n"
            f"Use send_email with this draft body to send it, or review and edit first."
        )

    async def _send_email(self, params: dict) -> str:
        to_addr = params.get("to", "").strip()
        subject = params.get("subject", "").strip()
        body = params.get("body", "").strip()

        if not to_addr or not subject or not body:
            return "Please provide to, subject, and body."

        smtp_host = self.config.get("smtp_host", "")
        smtp_port = int(self.config.get("smtp_port", 587))
        smtp_user = self.config.get("smtp_user", "")
        smtp_pass = self.config.get("smtp_pass", "")

        if not smtp_host or not smtp_user or not smtp_pass:
            draft = self._save_draft(to_addr, subject, body)
            return (
                f"SMTP is not configured — email saved as draft (ID: {draft['id']}).\n\n"
                f"To enable sending, add smtp_host, smtp_port, smtp_user, smtp_pass to the plugin config."
            )

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_user
            msg["To"] = to_addr
            msg.attach(MIMEText(body, "plain", "utf-8"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, [to_addr], msg.as_string())

            return (
                f"Email sent successfully.\n"
                f"  To:      {to_addr}\n"
                f"  Subject: {subject}\n"
                f"  Sent at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except smtplib.SMTPAuthenticationError:
            return "SMTP authentication failed. Check smtp_user and smtp_pass in config."
        except smtplib.SMTPException as e:
            return f"SMTP error: {e}"
        except Exception as e:
            logger.error(f"Send email failed: {e}")
            return f"Failed to send email: {e}"

    async def _list_drafts(self, params: dict) -> str:
        if not self.drafts:
            return "No email drafts saved yet. Use compose to create one."
        lines = [f"EMAIL DRAFTS  ({len(self.drafts)} total)", "─" * 70]
        for d in sorted(self.drafts, key=lambda x: x.get("created", ""), reverse=True):
            preview = d.get("body", "")[:50].replace("\n", " ")
            lines.append(
                f"  [{d['id']}]  {d.get('created','')[:16]}  "
                f"To: {d.get('recipient','')[:25]:<25}  {d.get('subject','')[:25]}"
            )
            lines.append(f"           {preview}...")
        return "\n".join(lines)

    async def _get_draft(self, params: dict) -> str:
        draft_id = params.get("id", "").strip()
        if not draft_id:
            return "Please provide a draft ID."
        for d in self.drafts:
            if d.get("id") == draft_id:
                return (
                    f"DRAFT [{d['id']}]\n"
                    f"  To:      {d.get('recipient')}\n"
                    f"  Subject: {d.get('subject')}\n"
                    f"  Tone:    {d.get('tone', 'professional')}\n"
                    f"  Created: {d.get('created', '')[:19]}\n\n"
                    f"{'─'*50}\n"
                    f"{d.get('body', '')}\n"
                    f"{'─'*50}"
                )
        return f"Draft '{draft_id}' not found."

    async def _delete_draft(self, params: dict) -> str:
        draft_id = params.get("id", "").strip()
        if not draft_id:
            return "Please provide a draft ID."
        for d in self.drafts:
            if d.get("id") == draft_id:
                self.drafts.remove(d)
                self._save()
                return f"Draft {draft_id} deleted (To: {d.get('recipient')}, Subject: {d.get('subject')})."
        return f"Draft '{draft_id}' not found."

    async def _improve_email(self, params: dict) -> str:
        text = params.get("text", "").strip()
        instruction = params.get("instruction", "").strip()
        if not text or not instruction:
            return "Please provide both text and instruction."

        prompt = (
            f"Improve the following email according to this instruction: {instruction}\n\n"
            f"Original email:\n{text}\n\n"
            f"Write only the improved email body — no commentary or explanation."
        )

        improved = self._call_ollama(prompt)
        if not improved:
            return f"AI unavailable. Original email unchanged:\n\n{text}"

        draft = self._save_draft("(improved)", "(improved)", improved)
        return (
            f"Email improved (saved as draft {draft['id']}).\n\n"
            f"{'─'*50}\n"
            f"{improved}\n"
            f"{'─'*50}"
        )

    async def _reply_template(self, params: dict) -> str:
        original_email = params.get("original_email", "").strip()
        reply_intent = params.get("reply_intent", "").strip()
        if not original_email or not reply_intent:
            return "Please provide original_email and reply_intent."

        prompt = (
            f"Write a professional reply to the following email.\n\n"
            f"Original email:\n{original_email}\n\n"
            f"My reply intention: {reply_intent}\n\n"
            f"Write only the reply email body — greeting, response, and sign-off. No commentary."
        )

        reply = self._call_ollama(prompt)
        if not reply:
            reply = (
                f"Thank you for your email.\n\n"
                f"{reply_intent}\n\n"
                f"Please let me know if you need anything further.\n\n"
                f"Best regards\n\n"
                f"[Note: AI unavailable — this is a basic template.]"
            )

        draft = self._save_draft("(reply)", "(reply)", reply)
        return (
            f"Reply template generated (saved as draft {draft['id']}).\n\n"
            f"{'─'*50}\n"
            f"{reply}\n"
            f"{'─'*50}"
        )
