"""
Expense Tracker Plugin — Track business expenses and income with categories.
Monthly/yearly summaries, profit/loss calculation. All local JSON storage.
"""

import json
import logging
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.expense_tracker")

EXPENSES_FILE = Path.home() / "NexusScripts" / "expenses.json"

CATEGORIES = [
    "Software", "Hardware", "Marketing", "Travel",
    "Meals", "Utilities", "Salary", "Freelance", "Other"
]


class ExpenseTrackerPlugin(BasePlugin):
    name = "expense_tracker"
    description = "Track business expenses and income — summaries, profit/loss, categories"
    icon = "💰"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.entries: list[dict] = []
        self._load()

    def _load(self):
        if EXPENSES_FILE.exists():
            try:
                self.entries = json.loads(EXPENSES_FILE.read_text(encoding="utf-8"))
                if not isinstance(self.entries, list):
                    self.entries = []
            except Exception as e:
                logger.warning(f"Could not load expenses: {e}")
                self.entries = []

    def _save(self):
        EXPENSES_FILE.parent.mkdir(parents=True, exist_ok=True)
        EXPENSES_FILE.write_text(
            json.dumps(self.entries, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )

    async def connect(self) -> bool:
        self._connected = True
        total_exp = sum(e["amount"] for e in self.entries if e.get("type") == "expense")
        total_inc = sum(e["amount"] for e in self.entries if e.get("type") == "income")
        self._status_message = f"{len(self.entries)} entries | Net: {total_inc - total_exp:.2f}"
        return True

    async def execute(self, action: str, params: dict) -> str:
        handler = {
            "add_expense":    self._add_expense,
            "add_income":     self._add_income,
            "get_summary":    self._get_summary,
            "list_expenses":  self._list_expenses,
            "get_profit_loss": self._get_profit_loss,
            "delete_entry":   self._delete_entry,
            "get_categories": self._get_categories,
        }.get(action)
        if not handler:
            return f"Unknown action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "add_expense",     "description": "Add a business expense",                            "params": ["amount", "category", "description", "currency"]},
            {"action": "add_income",      "description": "Record income or revenue",                          "params": ["amount", "description", "source"]},
            {"action": "get_summary",     "description": "Get expense/income summary for a period",           "params": ["period"]},
            {"action": "list_expenses",   "description": "List expenses, optionally filtered by category",    "params": ["category", "limit"]},
            {"action": "get_profit_loss", "description": "Calculate profit/loss for a month or all time",     "params": ["month"]},
            {"action": "delete_entry",    "description": "Delete an expense or income entry by ID",           "params": ["id"]},
            {"action": "get_categories",  "description": "List all available expense categories",             "params": []},
        ]

    def _period_filter(self, period: str) -> list[dict]:
        today = date.today()
        if period == "today":
            start = today.isoformat()
            end = today.isoformat()
        elif period == "week":
            start = (today - timedelta(days=today.weekday())).isoformat()
            end = today.isoformat()
        elif period == "month":
            start = today.replace(day=1).isoformat()
            end = today.isoformat()
        elif period == "year":
            start = today.replace(month=1, day=1).isoformat()
            end = today.isoformat()
        else:
            return self.entries
        return [e for e in self.entries if start <= e.get("date", "") <= end]

    async def _add_expense(self, params: dict) -> str:
        try:
            amount = float(params.get("amount", 0))
        except (ValueError, TypeError):
            return "Invalid amount. Please provide a numeric value."
        if amount <= 0:
            return "Amount must be greater than zero."

        category = params.get("category", "Other").strip()
        if category not in CATEGORIES:
            category = "Other"
        description = params.get("description", "").strip() or "No description"
        currency = params.get("currency", "USD").strip().upper()

        entry = {
            "id":          str(uuid.uuid4())[:8],
            "date":        date.today().isoformat(),
            "type":        "expense",
            "amount":      amount,
            "category":    category,
            "description": description,
            "currency":    currency,
            "created":     datetime.now().isoformat(),
        }
        self.entries.append(entry)
        self._save()
        return (
            f"Expense recorded.\n"
            f"  ID:          {entry['id']}\n"
            f"  Amount:      {currency} {amount:.2f}\n"
            f"  Category:    {category}\n"
            f"  Description: {description}\n"
            f"  Date:        {entry['date']}"
        )

    async def _add_income(self, params: dict) -> str:
        try:
            amount = float(params.get("amount", 0))
        except (ValueError, TypeError):
            return "Invalid amount. Please provide a numeric value."
        if amount <= 0:
            return "Amount must be greater than zero."

        description = params.get("description", "").strip() or "Income"
        source = params.get("source", "").strip() or "General"
        currency = params.get("currency", "USD").strip().upper()

        entry = {
            "id":          str(uuid.uuid4())[:8],
            "date":        date.today().isoformat(),
            "type":        "income",
            "amount":      amount,
            "category":    "Freelance",
            "description": description,
            "source":      source,
            "currency":    currency,
            "created":     datetime.now().isoformat(),
        }
        self.entries.append(entry)
        self._save()
        return (
            f"Income recorded.\n"
            f"  ID:          {entry['id']}\n"
            f"  Amount:      {currency} {amount:.2f}\n"
            f"  Source:      {source}\n"
            f"  Description: {description}\n"
            f"  Date:        {entry['date']}"
        )

    async def _get_summary(self, params: dict) -> str:
        period = params.get("period", "month").lower()
        filtered = self._period_filter(period)
        if not filtered:
            return f"No entries found for period: {period}."

        expenses = [e for e in filtered if e.get("type") == "expense"]
        income = [e for e in filtered if e.get("type") == "income"]
        total_exp = sum(e["amount"] for e in expenses)
        total_inc = sum(e["amount"] for e in income)
        net = total_inc - total_exp

        cat_breakdown = {}
        for e in expenses:
            cat = e.get("category", "Other")
            cat_breakdown[cat] = cat_breakdown.get(cat, 0) + e["amount"]

        lines = [
            f"SUMMARY — {period.upper()}",
            f"{'─'*40}",
            f"  Income:   {total_inc:>10.2f}",
            f"  Expenses: {total_exp:>10.2f}",
            f"  Net:      {net:>10.2f}  {'(profit)' if net >= 0 else '(loss)'}",
            f"\n  Expense Breakdown by Category:",
        ]
        for cat, amt in sorted(cat_breakdown.items(), key=lambda x: -x[1]):
            lines.append(f"    {cat:<15} {amt:>9.2f}")
        lines.append(f"\n  Entries: {len(filtered)} total ({len(expenses)} expenses, {len(income)} income)")
        return "\n".join(lines)

    async def _list_expenses(self, params: dict) -> str:
        category = params.get("category", "").strip()
        try:
            limit = int(params.get("limit", 20))
        except (ValueError, TypeError):
            limit = 20

        entries = self.entries
        if category:
            entries = [e for e in entries if e.get("category", "").lower() == category.lower()]

        entries = sorted(entries, key=lambda x: x.get("date", ""), reverse=True)[:limit]
        if not entries:
            return f"No entries found{f' for category {category}' if category else ''}."

        lines = [f"EXPENSES {'— ' + category if category else ''}  ({len(entries)} shown)", f"{'─'*70}"]
        for e in entries:
            t = "EXP" if e.get("type") == "expense" else "INC"
            lines.append(
                f"  [{e['id']}] {e['date']}  {t}  {e.get('currency','USD')} {e['amount']:>9.2f}"
                f"  {e.get('category',''):<12}  {e.get('description','')[:30]}"
            )
        return "\n".join(lines)

    async def _get_profit_loss(self, params: dict) -> str:
        month = params.get("month", "").strip()
        if month:
            entries = [e for e in self.entries if e.get("date", "").startswith(month)]
            label = month
        else:
            entries = self.entries
            label = "All Time"

        if not entries:
            return f"No entries found for {label}."

        total_inc = sum(e["amount"] for e in entries if e.get("type") == "income")
        total_exp = sum(e["amount"] for e in entries if e.get("type") == "expense")
        net = total_inc - total_exp
        margin = (net / total_inc * 100) if total_inc > 0 else 0

        return (
            f"PROFIT / LOSS — {label}\n"
            f"{'─'*40}\n"
            f"  Total Income:   {total_inc:>10.2f}\n"
            f"  Total Expenses: {total_exp:>10.2f}\n"
            f"  {'─'*28}\n"
            f"  Net P/L:        {net:>10.2f}  {'PROFIT' if net >= 0 else 'LOSS'}\n"
            f"  Profit Margin:  {margin:>9.1f}%\n"
            f"\n  Transactions: {len(entries)}"
        )

    async def _delete_entry(self, params: dict) -> str:
        entry_id = params.get("id", "").strip()
        if not entry_id:
            return "Please provide the entry ID to delete."
        for e in self.entries:
            if e.get("id") == entry_id:
                self.entries.remove(e)
                self._save()
                return f"Entry {entry_id} deleted ({e.get('type')} of {e.get('amount'):.2f} on {e.get('date')})."
        return f"Entry '{entry_id}' not found."

    async def _get_categories(self, params: dict) -> str:
        lines = ["Available expense categories:", ""]
        for i, cat in enumerate(CATEGORIES, 1):
            count = sum(1 for e in self.entries if e.get("category") == cat)
            total = sum(e["amount"] for e in self.entries if e.get("category") == cat)
            lines.append(f"  {i:>2}. {cat:<15}  ({count} entries, {total:.2f} total)")
        return "\n".join(lines)
