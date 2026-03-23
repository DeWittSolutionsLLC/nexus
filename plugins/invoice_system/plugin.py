"""
Invoice System Plugin — Professional invoicing for web dev businesses.
Generate, track, and manage client invoices. All local JSON storage.
"""

import json
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.invoice_system")

INVOICES_FILE = "memory/invoices.json"

STATUS_ICONS = {
    "draft":   "📝",
    "sent":    "📤",
    "paid":    "✅",
    "overdue": "🔴",
}


class InvoiceSystemPlugin(BasePlugin):
    name = "invoice_system"
    description = "Generate and track client invoices — billing, payments, revenue"
    icon = "💰"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.invoices: list[dict] = []
        self.settings: dict = {}
        self._load()

    def _load(self):
        path = Path(INVOICES_FILE)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.invoices = data.get("invoices", [])
                    self.settings = data.get("settings", {})
                elif isinstance(data, list):
                    self.invoices = data
            except Exception as e:
                logger.warning(f"Could not load invoices: {e}")

    def _save(self):
        path = Path(INVOICES_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"invoices": self.invoices, "settings": self.settings}, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    async def connect(self) -> bool:
        self._connected = True
        outstanding = sum(
            inv.get("total", 0) for inv in self.invoices
            if inv.get("status") in ("sent", "overdue")
        )
        self._status_message = f"{len(self.invoices)} invoices, £{outstanding:.0f} outstanding"
        return True

    async def execute(self, action: str, params: dict) -> str:
        actions = {
            "create_invoice":   self._create_invoice,
            "list_invoices":    self._list_invoices,
            "get_invoice":      self._get_invoice,
            "mark_sent":        self._mark_sent,
            "mark_paid":        self._mark_paid,
            "generate_text":    self._generate_text,
            "get_summary":      self._get_summary,
            "update_settings":  self._update_settings,
            "delete_invoice":   self._delete_invoice,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown invoice action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "create_invoice",  "description": "Create a new client invoice",                     "params": ["client", "hours", "rate", "description", "project"]},
            {"action": "list_invoices",   "description": "List all invoices with status and amounts",       "params": ["status_filter"]},
            {"action": "get_invoice",     "description": "Get full details for a specific invoice",         "params": ["invoice_number"]},
            {"action": "mark_sent",       "description": "Mark an invoice as sent to client",               "params": ["invoice_number"]},
            {"action": "mark_paid",       "description": "Mark an invoice as paid",                         "params": ["invoice_number", "payment_date"]},
            {"action": "generate_text",   "description": "Generate a formatted text invoice ready to send", "params": ["invoice_number"]},
            {"action": "get_summary",     "description": "Revenue summary — total earned, outstanding, paid", "params": ["period"]},
            {"action": "update_settings", "description": "Update invoice settings (your name, email, etc.)", "params": ["key", "value"]},
        ]

    async def _create_invoice(self, params: dict) -> str:
        client = params.get("client", "").strip()
        if not client:
            return "⚠️ Client name is required to create an invoice, sir."

        hours = float(params.get("hours", 0) or 0)
        rate = float(params.get("rate", self.settings.get("default_rate", 75)) or 75)
        description = params.get("description", "Web Development Services")
        project = params.get("project", "")
        amount = float(params.get("amount", 0) or 0)

        if not amount and hours and rate:
            amount = hours * rate

        if not amount:
            return "⚠️ Please specify either an amount or hours + rate, sir."

        tax_rate = float(self.settings.get("tax_rate", 0))
        tax_amount = amount * tax_rate / 100
        total = amount + tax_amount

        terms_days = int(self.settings.get("payment_terms_days", 30))
        issue_date = date.today()
        due_date = issue_date + timedelta(days=terms_days)

        inv_num = f"INV-{len(self.invoices) + 1:04d}"

        invoice = {
            "id":             len(self.invoices) + 1,
            "invoice_number": inv_num,
            "client":         client,
            "project":        project,
            "issue_date":     issue_date.isoformat(),
            "due_date":       due_date.isoformat(),
            "status":         "draft",
            "items": [{
                "description": description,
                "hours":       hours,
                "rate":        rate,
                "amount":      amount,
            }],
            "subtotal":    amount,
            "tax_rate":    tax_rate,
            "tax_amount":  tax_amount,
            "total":       total,
            "notes":       params.get("notes", self.settings.get("default_notes", "Payment due within 30 days.")),
            "created":     datetime.now().isoformat(),
        }
        self.invoices.append(invoice)
        self._save()

        return (
            f"💰 Invoice created, sir.\n\n"
            f"  Number:  {inv_num}\n"
            f"  Client:  {client}\n"
            f"  Project: {project or 'General'}\n"
            f"  Amount:  £{amount:.2f}"
            + (f"  + Tax ({tax_rate}%): £{tax_amount:.2f}" if tax_amount else "") +
            f"\n  Total:   £{total:.2f}\n"
            f"  Due:     {due_date.strftime('%B %d, %Y')}\n\n"
            f"Say 'mark invoice {inv_num} sent' when you've sent it, sir."
        )

    async def _list_invoices(self, params: dict) -> str:
        if not self.invoices:
            return "📋 No invoices on record yet, sir. Say 'create invoice' to get started."

        # Auto-mark overdue
        today = date.today().isoformat()
        for inv in self.invoices:
            if inv.get("status") == "sent" and inv.get("due_date", "") < today:
                inv["status"] = "overdue"
        self._save()

        status_filter = params.get("status_filter", "").lower()
        invoices = [i for i in self.invoices if not status_filter or i.get("status") == status_filter]

        if not invoices:
            return f"No invoices with status '{status_filter}'."

        lines = [f"💰 INVOICES ({len(invoices)} shown)\n{'─'*65}"]
        for inv in sorted(invoices, key=lambda x: x.get("issue_date", ""), reverse=True):
            icon = STATUS_ICONS.get(inv["status"], "📄")
            num = inv["invoice_number"]
            client = inv["client"]
            total = inv["total"]
            due = inv.get("due_date", "")
            lines.append(f"\n  {icon} {num}  {client:<25}  £{total:>8.2f}  Due: {due}")

        # Totals
        outstanding = sum(i["total"] for i in invoices if i["status"] in ("sent", "overdue"))
        paid_total = sum(i["total"] for i in invoices if i["status"] == "paid")
        if outstanding or paid_total:
            lines.append(f"\n{'─'*65}")
            if outstanding:
                lines.append(f"  Outstanding: £{outstanding:.2f}")
            if paid_total:
                lines.append(f"  Paid total:  £{paid_total:.2f}")

        return "\n".join(lines)

    async def _get_invoice(self, params: dict) -> str:
        inv_num = params.get("invoice_number", "").upper()
        invoice = self._find(inv_num)
        if not invoice:
            return f"⚠️ Invoice '{inv_num}' not found, sir."
        return self._generate_text_internal(invoice)

    async def _mark_sent(self, params: dict) -> str:
        inv_num = params.get("invoice_number", "").upper()
        invoice = self._find(inv_num)
        if not invoice:
            return f"⚠️ Invoice '{inv_num}' not found, sir."
        invoice["status"] = "sent"
        invoice["sent_date"] = date.today().isoformat()
        self._save()
        return f"📤 Invoice {inv_num} marked as sent to {invoice['client']}. Due: {invoice['due_date']}."

    async def _mark_paid(self, params: dict) -> str:
        inv_num = params.get("invoice_number", "").upper()
        payment_date = params.get("payment_date", date.today().isoformat())
        invoice = self._find(inv_num)
        if not invoice:
            return f"⚠️ Invoice '{inv_num}' not found, sir."
        invoice["status"] = "paid"
        invoice["payment_date"] = payment_date
        self._save()
        return f"✅ Invoice {inv_num} marked as paid (£{invoice['total']:.2f}) — {payment_date}. Excellent."

    async def _generate_text(self, params: dict) -> str:
        inv_num = params.get("invoice_number", "").upper()
        invoice = self._find(inv_num)
        if not invoice:
            return f"⚠️ Invoice '{inv_num}' not found, sir."
        return self._generate_text_internal(invoice)

    def _generate_text_internal(self, inv: dict) -> str:
        your_name = self.settings.get("your_name", "Your Name")
        your_email = self.settings.get("your_email", "your@email.com")
        your_address = self.settings.get("your_address", "")

        lines = [
            "═" * 60,
            f"  INVOICE",
            f"  {inv['invoice_number']}",
            "═" * 60,
            f"  FROM:  {your_name}",
        ]
        if your_address:
            lines.append(f"         {your_address}")
        lines.append(f"         {your_email}")
        lines.append("")
        lines.append(f"  TO:    {inv['client']}")
        lines.append("")
        lines.append(f"  Issue Date: {inv['issue_date']}")
        lines.append(f"  Due Date:   {inv['due_date']}")
        if inv.get("project"):
            lines.append(f"  Project:    {inv['project']}")
        lines.append("")
        lines.append("─" * 60)
        lines.append(f"  {'DESCRIPTION':<35}  {'HRS':>5}  {'RATE':>8}  {'AMOUNT':>9}")
        lines.append("─" * 60)

        for item in inv.get("items", []):
            desc = item.get("description", "Services")[:35]
            hrs = f"{item.get('hours', 0):.1f}" if item.get("hours") else "-"
            rate_str = f"£{item.get('rate', 0):.2f}" if item.get("rate") else "-"
            amt = f"£{item.get('amount', 0):.2f}"
            lines.append(f"  {desc:<35}  {hrs:>5}  {rate_str:>8}  {amt:>9}")

        lines.append("─" * 60)
        lines.append(f"  {'Subtotal':<50}  £{inv.get('subtotal', 0):>8.2f}")
        if inv.get("tax_amount"):
            lines.append(f"  {'Tax (' + str(inv['tax_rate']) + '%)':<50}  £{inv['tax_amount']:>8.2f}")
        lines.append(f"  {'TOTAL':<50}  £{inv.get('total', 0):>8.2f}")
        lines.append("═" * 60)
        if inv.get("notes"):
            lines.append(f"\n  Notes: {inv['notes']}")
        lines.append(f"  Status: {STATUS_ICONS.get(inv['status'], '📄')} {inv['status'].upper()}")

        return "\n".join(lines)

    async def _get_summary(self, params: dict) -> str:
        if not self.invoices:
            return "No invoices on record yet, sir."

        # Auto-mark overdue
        today = date.today().isoformat()
        for inv in self.invoices:
            if inv.get("status") == "sent" and inv.get("due_date", "") < today:
                inv["status"] = "overdue"
        self._save()

        total = sum(i["total"] for i in self.invoices)
        paid = sum(i["total"] for i in self.invoices if i["status"] == "paid")
        outstanding = sum(i["total"] for i in self.invoices if i["status"] in ("sent", "overdue"))
        overdue = sum(i["total"] for i in self.invoices if i["status"] == "overdue")
        draft = sum(i["total"] for i in self.invoices if i["status"] == "draft")

        return (
            f"💰 REVENUE SUMMARY\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  Total invoiced:  £{total:.2f}  ({len(self.invoices)} invoices)\n"
            f"  ✅ Paid:         £{paid:.2f}\n"
            f"  📤 Outstanding:  £{outstanding:.2f}\n"
            f"  🔴 Overdue:      £{overdue:.2f}\n"
            f"  📝 Draft:        £{draft:.2f}"
        )

    async def _update_settings(self, params: dict) -> str:
        key = params.get("key", "")
        value = params.get("value", "")
        if not key:
            return "⚠️ Please specify a setting key, sir."
        self.settings[key] = value
        self._save()
        return f"✅ Invoice setting '{key}' updated to '{value}'."

    async def _delete_invoice(self, params: dict) -> str:
        inv_num = params.get("invoice_number", "").upper()
        invoice = self._find(inv_num)
        if not invoice:
            return f"⚠️ Invoice '{inv_num}' not found."
        self.invoices.remove(invoice)
        self._save()
        return f"🗑️ Invoice {inv_num} deleted."

    def _find(self, inv_num: str) -> dict | None:
        inv_num = inv_num.upper()
        for inv in self.invoices:
            if inv["invoice_number"].upper() == inv_num:
                return inv
        # Try partial match
        for inv in self.invoices:
            if inv_num in inv["invoice_number"].upper():
                return inv
        return None
