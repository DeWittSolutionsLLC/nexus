"""
Web Remote Plugin — Control Nexus from any browser on your local network.

Access from your phone at:  http://[YOUR-PC-IP]:7777
Find your IP with:           ipconfig (look for IPv4 under your WiFi adapter)

No install needed on phone — just open the browser and go.
Works on iOS Safari, Android Chrome, any browser.
"""

import asyncio
import json
import logging
import socket
import threading
import time
from datetime import datetime

from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.web_remote")


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


MOBILE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>NEXUS Remote</title>
<style>
  :root {
    --bg:      #050A18;
    --bg2:     #0A1228;
    --bg3:     #0F1E3C;
    --accent:  #00D4FF;
    --text:    #E8F4FF;
    --muted:   #3A6B85;
    --success: #00FF88;
    --error:   #FF3030;
    --user:    #003870;
    --bot:     #080F22;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    height: 100dvh;
    display: flex;
    flex-direction: column;
  }
  header {
    background: var(--bg2);
    padding: 12px 16px;
    display: flex;
    align-items: center;
    gap: 10px;
    border-bottom: 1px solid var(--bg3);
    flex-shrink: 0;
  }
  header h1 { font-size: 16px; font-weight: 700; color: var(--accent); }
  header span { font-size: 11px; color: var(--muted); }
  .dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--success);
    animation: pulse 2s infinite;
    flex-shrink: 0;
  }
  @keyframes pulse {
    0%,100% { opacity: 1; }
    50%      { opacity: 0.4; }
  }
  #chat {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    -webkit-overflow-scrolling: touch;
  }
  .msg {
    max-width: 85%;
    padding: 10px 14px;
    border-radius: 14px;
    font-size: 14px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .msg.user { background: var(--user); align-self: flex-end; }
  .msg.bot  { background: var(--bot); align-self: flex-start; border: 1px solid var(--bg3); }
  .msg.sys  {
    background: transparent;
    color: var(--accent);
    font-family: 'Courier New', monospace;
    font-size: 12px;
    align-self: flex-start;
  }
  .msg-hdr  { font-size: 11px; color: var(--accent); font-weight: 700; margin-bottom: 4px; }
  .msg-time { font-size: 10px; color: var(--muted); margin-top: 4px; text-align: right; }
  .thinking { color: var(--accent); font-size: 13px; font-style: italic; align-self: flex-start; }
  footer {
    background: var(--bg2);
    padding: 10px 12px;
    border-top: 1px solid var(--bg3);
    display: flex;
    gap: 8px;
    flex-shrink: 0;
  }
  #input {
    flex: 1;
    background: var(--bg3);
    border: 1px solid #1A3A5C;
    border-radius: 10px;
    color: var(--text);
    font-size: 15px;
    padding: 10px 14px;
    outline: none;
    -webkit-appearance: none;
  }
  #input:focus { border-color: var(--accent); }
  #send {
    background: var(--accent);
    border: none;
    border-radius: 10px;
    color: #050A18;
    font-size: 15px;
    font-weight: 700;
    padding: 10px 18px;
    cursor: pointer;
    flex-shrink: 0;
    -webkit-appearance: none;
  }
  #send:active { opacity: 0.75; }
  .quick-btns {
    display: flex;
    gap: 6px;
    padding: 0 12px 8px;
    overflow-x: auto;
    flex-shrink: 0;
    scrollbar-width: none;
  }
  .quick-btns::-webkit-scrollbar { display: none; }
  .qb {
    background: var(--bg3);
    border: 1px solid #1A3A5C;
    border-radius: 20px;
    color: var(--text);
    font-size: 12px;
    padding: 6px 12px;
    cursor: pointer;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .qb:active { background: #1A3A5C; }
</style>
</head>
<body>
<header>
  <div class="dot" id="dot"></div>
  <div>
    <h1>◆ NEXUS</h1>
    <span>J.A.R.V.I.S. Remote</span>
  </div>
</header>

<div id="chat">
  <div class="msg sys">◆ NEXUS remote interface online.</div>
  <div class="msg bot">
    <div class="msg-hdr">◆ NEXUS</div>
    Good day, sir. Remote access established.<br>Type any command below.
  </div>
</div>

<div class="quick-btns">
  <button class="qb" onclick="send('Good morning')">☀️ Morning</button>
  <button class="qb" onclick="send('Check my email')">📧 Email</button>
  <button class="qb" onclick="send('System stats')">⚡ Stats</button>
  <button class="qb" onclick="send('Get weather')">🌤️ Weather</button>
  <button class="qb" onclick="send('List my projects')">🚀 Projects</button>
  <button class="qb" onclick="send('List my invoices')">💰 Invoices</button>
  <button class="qb" onclick="send('Check uptime')">🛡️ Uptime</button>
  <button class="qb" onclick="send('Check urgent')">🚨 Urgent</button>
</div>

<footer>
  <input id="input" type="text" placeholder="Command or question, sir..." autocomplete="off"
         onkeydown="if(event.key==='Enter') send()">
  <button id="send" onclick="send()">Send</button>
</footer>

<script>
const chat = document.getElementById('chat');
const input = document.getElementById('input');

function ts() {
  const d = new Date();
  return d.getHours().toString().padStart(2,'0') + ':' + d.getMinutes().toString().padStart(2,'0');
}

function addMsg(text, type) {
  const div = document.createElement('div');
  div.className = 'msg ' + type;
  if (type === 'bot') {
    div.innerHTML = '<div class="msg-hdr">◆ NEXUS</div>' +
      escHtml(text) + '<div class="msg-time">' + ts() + '</div>';
  } else if (type === 'user') {
    div.textContent = text;
  } else {
    div.textContent = text;
  }
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function escHtml(t) {
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\\n/g,'<br>');
}

async function send(text) {
  const cmd = (text || input.value).trim();
  if (!cmd) return;
  input.value = '';

  addMsg(cmd, 'user');

  const thinking = document.createElement('div');
  thinking.className = 'thinking';
  thinking.textContent = '◆ Analyzing...';
  chat.appendChild(thinking);
  chat.scrollTop = chat.scrollHeight;

  try {
    const resp = await fetch('/api/command', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({command: cmd})
    });
    const data = await resp.json();
    thinking.remove();
    addMsg(data.response || 'No response.', 'bot');
  } catch(e) {
    thinking.remove();
    addMsg('Error: ' + e.message, 'sys');
  }
}

// Heartbeat
async function heartbeat() {
  try {
    const r = await fetch('/api/ping');
    document.getElementById('dot').style.background = r.ok ? '#00FF88' : '#FF3030';
  } catch { document.getElementById('dot').style.background = '#FF3030'; }
}
setInterval(heartbeat, 10000);
</script>
</body>
</html>"""


class WebRemotePlugin(BasePlugin):
    name = "web_remote"
    description = "Control Nexus from your phone browser on local network"
    icon = "🌐"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self.port: int = int(config.get("port", 7777))
        self.host: str = config.get("host", "0.0.0.0")

        self._assistant = None
        self._plugin_manager = None
        self._server = None
        self._server_thread: threading.Thread | None = None
        self._local_ip = _get_local_ip()

    def set_dependencies(self, assistant, plugin_manager):
        self._assistant = assistant
        self._plugin_manager = plugin_manager

    # ── Lifecycle ──────────────────────────────────────────────

    async def connect(self) -> bool:
        try:
            from flask import Flask  # noqa: F401
        except ImportError:
            self._status_message = "flask not installed (pip install flask)"
            self._connected = False
            return False

        self._server_thread = threading.Thread(target=self._run_server, daemon=True, name="web-remote")
        self._server_thread.start()

        time.sleep(0.5)  # Give Flask a moment to start

        self._connected = True
        self._status_message = f"http://{self._local_ip}:{self.port}"
        logger.info(f"Web remote: http://{self._local_ip}:{self.port}")
        return True

    async def disconnect(self):
        self._connected = False
        self._status_message = "Disconnected"

    # ── Flask server ───────────────────────────────────────────

    def _run_server(self):
        from flask import Flask, jsonify, request as flask_request
        import flask.cli
        import logging as _log

        # Suppress Flask startup banner and werkzeug access/error logs
        flask.cli.show_server_banner = lambda *args, **kwargs: None
        werkzeug_log = _log.getLogger("werkzeug")
        werkzeug_log.setLevel(_log.CRITICAL)

        # Filter out harmless SSL-probe "Bad request version" noise
        # (happens when a browser or phone tries https:// on a plain http server)
        class _SSLProbeFilter(_log.Filter):
            def filter(self, record):
                return "Bad request version" not in record.getMessage()

        werkzeug_log.addFilter(_SSLProbeFilter())

        app = Flask(__name__)
        app.logger.setLevel(_log.CRITICAL)

        @app.route("/")
        def index():
            from flask import Response
            return Response(MOBILE_HTML, mimetype="text/html")

        @app.route("/api/ping")
        def ping():
            return jsonify({"status": "ok", "time": datetime.now().strftime("%H:%M:%S")})

        @app.route("/api/command", methods=["POST"])
        def command():
            data = flask_request.get_json(force=True) or {}
            cmd = data.get("command", "").strip()
            if not cmd:
                return jsonify({"response": "Empty command."})

            result_holder: dict = {"text": None}
            done = threading.Event()

            async def _process():
                try:
                    if not (self._assistant and self._plugin_manager):
                        result_holder["text"] = "Assistant not ready yet."
                        return
                    caps = self._plugin_manager.get_all_capabilities()
                    result = await self._assistant.process_input(cmd, caps)
                    rtype = result.get("type", "conversation")

                    if rtype == "conversation":
                        result_holder["text"] = result.get("message", "...")

                    elif rtype == "action":
                        plugin_name = result.get("plugin", "")
                        action = result.get("action", "")
                        explanation = result.get("explanation", "")
                        plugin = self._plugin_manager.get_plugin(plugin_name)
                        if plugin and plugin.is_connected:
                            out = await plugin.execute(action, result.get("params", {}))
                            prefix = f">> {explanation}\n\n" if explanation else ""
                            result_holder["text"] = prefix + out
                        elif plugin:
                            result_holder["text"] = f"⚠️ {plugin_name} is not connected."
                        else:
                            result_holder["text"] = f"⚠️ Plugin '{plugin_name}' not found."

                    elif rtype == "multi_action":
                        parts = [f">> {result.get('explanation', '')}"]
                        for i, step in enumerate(result.get("steps", []), 1):
                            p = self._plugin_manager.get_plugin(step.get("plugin", ""))
                            if p and p.is_connected:
                                out = await p.execute(step["action"], step.get("params", {}))
                                parts.append(f"Step {i}: {out}")
                        result_holder["text"] = "\n\n".join(parts)

                    else:
                        result_holder["text"] = str(result)

                except Exception as e:
                    result_holder["text"] = f"Error: {str(e)}"
                finally:
                    done.set()

            # Route through the dedicated event loop
            loop = self._get_loop()
            if loop:
                asyncio.run_coroutine_threadsafe(_process(), loop)
                done.wait(timeout=45)
            else:
                result_holder["text"] = "Event loop not ready."

            return jsonify({"response": result_holder.get("text") or "No response."})

        @app.route("/api/status")
        def status():
            plugins = []
            if self._plugin_manager:
                for info in self._plugin_manager.get_status_summary():
                    plugins.append({
                        "name":      info["name"],
                        "icon":      info["icon"],
                        "connected": info["connected"],
                        "status":    info["status"],
                    })
            return jsonify({"plugins": plugins, "time": datetime.now().isoformat()})

        try:
            app.run(host=self.host, port=self.port, threaded=True, use_reloader=False)
        except OSError as e:
            logger.error(f"Web remote failed to bind port {self.port}: {e}")
            self._status_message = f"Port {self.port} in use"
            self._connected = False

    def _get_loop(self) -> asyncio.AbstractEventLoop | None:
        """Get a running event loop to schedule coroutines on."""
        try:
            # Try the assistant's stored loop (set by AppWindow)
            if self._assistant and hasattr(self._assistant, "_remote_loop"):
                return self._assistant._remote_loop
            # Fall back: find any running loop
            import gc
            for obj in gc.get_objects():
                if isinstance(obj, asyncio.BaseEventLoop) and obj.is_running():
                    return obj
        except Exception:
            pass
        return None

    # ── Plugin interface ───────────────────────────────────────

    async def execute(self, action: str, params: dict) -> str:
        actions = {
            "get_url":    self._exec_url,
            "get_status": self._exec_status,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown web_remote action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "get_url",    "description": "Get the URL to access Nexus from your phone", "params": []},
            {"action": "get_status", "description": "Get web remote server status",                 "params": []},
        ]

    async def _exec_url(self, params: dict) -> str:
        if self._connected:
            return (
                f"🌐 Web Remote is running, sir.\n\n"
                f"  Local URL:  http://{self._local_ip}:{self.port}\n\n"
                f"Open this on your phone while on the same WiFi network."
            )
        return "⚠️ Web remote is not running."

    async def _exec_status(self, params: dict) -> str:
        status = "running" if self._connected else "stopped"
        return (
            f"🌐 Web Remote Server\n"
            f"  Status: {status}\n"
            f"  URL:    http://{self._local_ip}:{self.port}\n"
            f"  Bind:   {self.host}:{self.port}"
        )
