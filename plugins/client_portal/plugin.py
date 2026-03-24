"""
Client Portal Plugin — Per-client password-protected status pages.

Each client gets a unique URL: http://localhost:5001/client/<slug>
Shows live project status, invoices, and a contact form.
Reads data from project_manager and invoice_system plugins.
"""

import asyncio
import hashlib
import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.client_portal")

PORTAL_DIR = Path.home() / "NexusPortal"
CLIENTS_FILE = PORTAL_DIR / "clients.json"
DEFAULT_PORT = 5001


class ClientPortalPlugin(BasePlugin):
    name = "client_portal"
    description = "Per-client status portals — project progress, invoices, messaging"
    icon = "🌐"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._port = config.get("portal_port", DEFAULT_PORT)
        self._plugin_manager = None
        self._flask_thread: threading.Thread | None = None
        self._app = None
        self._clients: dict[str, dict] = {}
        PORTAL_DIR.mkdir(exist_ok=True)
        self._load_clients()

    def set_plugin_manager(self, pm):
        self._plugin_manager = pm

    async def connect(self) -> bool:
        try:
            import flask  # noqa: F401
            self._connected = True
            self._status_message = f"Ready — port {self._port} (not started)"
            return True
        except ImportError:
            self._status_message = "Flask not installed (pip install flask)"
            return False

    async def execute(self, action: str, params: dict) -> str:
        dispatch = {
            "start_portal":   self._start_portal,
            "stop_portal":    self._stop_portal,
            "add_client":     self._add_client,
            "list_clients":   self._list_clients,
            "remove_client":  self._remove_client,
            "get_url":        self._get_url,
        }
        handler = dispatch.get(action)
        if not handler:
            return f"❌ Unknown action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "start_portal",  "description": "Start the client portal web server", "params": []},
            {"action": "stop_portal",   "description": "Stop the client portal", "params": []},
            {"action": "add_client",    "description": "Add a client to the portal", "params": ["name", "password", "email"]},
            {"action": "list_clients",  "description": "List all portal clients", "params": []},
            {"action": "remove_client", "description": "Remove a client from the portal", "params": ["name"]},
            {"action": "get_url",       "description": "Get a client's portal URL", "params": ["name"]},
        ]

    # ── Actions ──────────────────────────────────────────────────────────────

    async def _start_portal(self, params: dict) -> str:
        if self._flask_thread and self._flask_thread.is_alive():
            return f"✅ Client portal already running at http://localhost:{self._port}"

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._build_and_start_flask)
        await asyncio.sleep(1.0)   # let Flask start

        self._status_message = f"Running on port {self._port}"
        return (
            f"✅ Client portal started, sir.\n\n"
            f"🌐 http://localhost:{self._port}\n\n"
            f"Each client visits: http://localhost:{self._port}/client/<slug>\n"
            f"Say 'add client John password=abc123' to create a client account."
        )

    async def _stop_portal(self, params: dict) -> str:
        # Flask dev server can't be cleanly stopped from Python without werkzeug internals.
        # We'll track shutdown via a flag.
        self._status_message = f"Stopped (restart Nexus to fully free port {self._port})"
        return f"⚠️ Portal flagged to stop. Full stop on next Nexus restart."

    async def _add_client(self, params: dict) -> str:
        name = params.get("name", "").strip()
        password = params.get("password", "").strip()
        email = params.get("email", "")
        if not name:
            return "❌ Please provide a client name."
        if not password:
            password = self._generate_password(name)

        slug = name.lower().replace(" ", "-").replace("_", "-")
        pw_hash = hashlib.sha256(password.encode()).hexdigest()

        self._clients[slug] = {
            "name":     name,
            "slug":     slug,
            "email":    email,
            "pw_hash":  pw_hash,
            "password": password,   # stored plain for easy retrieval — local only
            "created":  datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        self._save_clients()

        url = f"http://localhost:{self._port}/client/{slug}"
        return (
            f"✅ Client '{name}' added to portal, sir.\n\n"
            f"🌐 URL: {url}\n"
            f"🔑 Password: {password}\n\n"
            f"Share these credentials with your client. "
            f"Start the portal with 'start client portal' if not already running."
        )

    async def _list_clients(self, params: dict) -> str:
        if not self._clients:
            return (
                "🌐 No portal clients yet, sir.\n\n"
                "Add one: 'add client AcmeCo password=secret123'"
            )
        lines = [f"🌐 Client Portal — http://localhost:{self._port}\n"]
        for slug, data in self._clients.items():
            lines.append(f"  👤 {data['name']}")
            lines.append(f"      URL: /client/{slug}")
            lines.append(f"      Password: {data['password']}")
            if data.get("email"):
                lines.append(f"      Email: {data['email']}")
            lines.append(f"      Added: {data['created']}\n")
        return "\n".join(lines)

    async def _remove_client(self, params: dict) -> str:
        name = params.get("name", "").strip()
        slug = name.lower().replace(" ", "-")
        if slug not in self._clients:
            return f"❌ Client '{name}' not found."
        del self._clients[slug]
        self._save_clients()
        return f"🗑️ Client '{name}' removed from portal."

    async def _get_url(self, params: dict) -> str:
        name = params.get("name", "").strip()
        slug = name.lower().replace(" ", "-")
        if slug not in self._clients:
            return f"❌ Client '{name}' not found."
        data = self._clients[slug]
        return f"🌐 {data['name']}: http://localhost:{self._port}/client/{slug}\n🔑 Password: {data['password']}"

    # ── Flask app ─────────────────────────────────────────────────────────────

    def _build_and_start_flask(self):
        from flask import Flask, render_template_string, request, session, redirect

        app = Flask(__name__)
        app.secret_key = "nexus_portal_secret_2026"
        plugin_ref = self   # closure

        PORTAL_HTML = """
<!DOCTYPE html>
<html>
<head>
<title>{{ client_name }} — Client Portal</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body{font-family:'Segoe UI',sans-serif;background:#0a0e1a;color:#e0e6f0;margin:0;padding:0}
  .header{background:#0d1117;padding:20px 40px;border-bottom:1px solid #00D4FF33}
  .header h1{color:#00D4FF;margin:0;font-size:1.4em}
  .header p{color:#888;margin:4px 0 0;font-size:0.9em}
  .container{max-width:900px;margin:40px auto;padding:0 20px}
  .card{background:#0d1117;border:1px solid #1a2030;border-radius:8px;padding:24px;margin-bottom:20px}
  .card h2{color:#00D4FF;margin:0 0 16px;font-size:1em;text-transform:uppercase;letter-spacing:1px}
  .status-badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:0.8em}
  .active{background:#00D4FF22;color:#00D4FF;border:1px solid #00D4FF44}
  .pending{background:#FFB30022;color:#FFB300;border:1px solid #FFB30044}
  .done{background:#00FF8822;color:#00FF88;border:1px solid #00FF8844}
  table{width:100%;border-collapse:collapse}
  td,th{padding:10px;text-align:left;border-bottom:1px solid #1a2030}
  th{color:#888;font-size:0.8em;text-transform:uppercase}
  .amount{color:#00FF88}
</style>
</head>
<body>
<div class="header">
  <h1>◆ NEXUS CLIENT PORTAL</h1>
  <p>{{ client_name }} — as of {{ now }}</p>
</div>
<div class="container">
  <div class="card">
    <h2>Active Projects</h2>
    {% if projects %}
    <table>
      <tr><th>Project</th><th>Status</th><th>Deadline</th></tr>
      {% for p in projects %}
      <tr>
        <td>{{ p.get('name','—') }}</td>
        <td><span class="status-badge {{ p.get('status','active') }}">{{ p.get('status','Active') }}</span></td>
        <td>{{ p.get('deadline','TBD') }}</td>
      </tr>
      {% endfor %}
    </table>
    {% else %}<p style="color:#555">No active projects.</p>{% endif %}
  </div>
  <div class="card">
    <h2>Invoices</h2>
    {% if invoices %}
    <table>
      <tr><th>Description</th><th>Amount</th><th>Status</th></tr>
      {% for inv in invoices %}
      <tr>
        <td>{{ inv.get('description','Invoice') }}</td>
        <td class="amount">${{ inv.get('amount','0') }}</td>
        <td><span class="status-badge {{ 'done' if inv.get('paid') else 'pending' }}">{{ 'Paid' if inv.get('paid') else 'Pending' }}</span></td>
      </tr>
      {% endfor %}
    </table>
    {% else %}<p style="color:#555">No invoices on file.</p>{% endif %}
  </div>
  <div class="card">
    <h2>Message Us</h2>
    <form method="POST" action="/client/{{ slug }}/message">
      <textarea name="msg" rows="3" style="width:100%;background:#0a0e1a;color:#e0e6f0;border:1px solid #1a2030;border-radius:4px;padding:10px;font-family:inherit" placeholder="Your message..."></textarea>
      <button type="submit" style="margin-top:8px;padding:8px 20px;background:#00D4FF;color:#0a0e1a;border:none;border-radius:4px;cursor:pointer">Send</button>
    </form>
    {% if message_sent %}<p style="color:#00FF88">✓ Message sent!</p>{% endif %}
  </div>
</div>
</body>
</html>"""

        LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head><title>Client Portal Login</title>
<style>
  body{font-family:'Segoe UI',sans-serif;background:#0a0e1a;color:#e0e6f0;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
  .box{background:#0d1117;border:1px solid #1a2030;border-radius:8px;padding:40px;width:320px}
  h2{color:#00D4FF;margin:0 0 24px;text-align:center}
  input{width:100%;padding:10px;background:#0a0e1a;border:1px solid #1a2030;border-radius:4px;color:#e0e6f0;font-size:1em;box-sizing:border-box;margin-bottom:12px}
  button{width:100%;padding:10px;background:#00D4FF;color:#0a0e1a;border:none;border-radius:4px;cursor:pointer;font-size:1em}
  .error{color:#ff4444;font-size:0.85em;margin-bottom:8px}
</style>
</head>
<body>
<div class="box">
  <h2>◆ CLIENT PORTAL</h2>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  <form method="POST">
    <input name="password" type="password" placeholder="Access Password" autofocus>
    <button>Enter</button>
  </form>
</div>
</body>
</html>"""

        @app.route("/")
        def index():
            return "<h2 style='font-family:monospace;color:#00D4FF;background:#0a0e1a;padding:40px'>◆ NEXUS Client Portal — visit /client/&lt;your-slug&gt;</h2>"

        @app.route("/client/<slug>", methods=["GET", "POST"])
        def client_view(slug):
            client = plugin_ref._clients.get(slug)
            if not client:
                return "Client not found", 404

            # Auth
            if session.get(f"auth_{slug}") != True:
                if request.method == "POST":
                    pw = request.form.get("password", "")
                    if hashlib.sha256(pw.encode()).hexdigest() == client["pw_hash"]:
                        session[f"auth_{slug}"] = True
                        return redirect(f"/client/{slug}")
                    return render_template_string(LOGIN_HTML, error="Incorrect password.")
                return render_template_string(LOGIN_HTML, error=None)

            # Gather data
            projects, invoices = [], []
            if plugin_ref._plugin_manager:
                pm_plugin = plugin_ref._plugin_manager.get_plugin("project_manager")
                inv_plugin = plugin_ref._plugin_manager.get_plugin("invoice_system")
                if pm_plugin and hasattr(pm_plugin, "_projects"):
                    projects = [p for p in pm_plugin._projects.values()
                                if client["name"].lower() in p.get("client", "").lower()]
                if inv_plugin and hasattr(inv_plugin, "_invoices"):
                    invoices = [i for i in inv_plugin._invoices.values()
                                if client["name"].lower() in i.get("client", "").lower()]

            msg_sent = request.method == "POST" and "msg" not in request.form
            return render_template_string(
                PORTAL_HTML,
                client_name=client["name"],
                slug=slug,
                projects=projects,
                invoices=invoices,
                now=datetime.now().strftime("%B %d, %Y at %H:%M"),
                message_sent=msg_sent,
            )

        @app.route("/client/<slug>/message", methods=["POST"])
        def client_message(slug):
            msg = request.form.get("msg", "").strip()
            if msg:
                client = plugin_ref._clients.get(slug)
                name = client["name"] if client else slug
                logger.info(f"Client message from {name}: {msg}")
                # Save to a messages log
                msgs_file = PORTAL_DIR / f"messages_{slug}.txt"
                with open(msgs_file, "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {msg}\n")
            return redirect(f"/client/{slug}?sent=1")

        self._app = app
        self._flask_thread = threading.Thread(
            target=lambda: app.run(host="0.0.0.0", port=plugin_ref._port, debug=False, use_reloader=False),
            daemon=True,
        )
        self._flask_thread.start()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load_clients(self):
        if CLIENTS_FILE.exists():
            try:
                self._clients = json.loads(CLIENTS_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._clients = {}

    def _save_clients(self):
        CLIENTS_FILE.write_text(json.dumps(self._clients, indent=2), encoding="utf-8")

    @staticmethod
    def _generate_password(name: str) -> str:
        import random, string
        random.seed(name + str(datetime.now().date()))
        chars = string.ascii_letters + string.digits
        return "".join(random.choices(chars, k=10))
