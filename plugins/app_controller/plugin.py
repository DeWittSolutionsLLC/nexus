from core.plugin_manager import BasePlugin
import logging
import subprocess
import ctypes
import ctypes.wintypes

logger = logging.getLogger("nexus.plugins.app_controller")

KNOWN_APPS: dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "browser": "msedge.exe",
    "edge": "msedge.exe",
    "chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "vscode": "code.exe",
    "explorer": "explorer.exe",
    "spotify": "Spotify.exe",
    "discord": "Discord.exe",
    "terminal": "wt.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "paint": "mspaint.exe",
    "wordpad": "wordpad.exe",
}


class AppControllerPlugin(BasePlugin):
    name = "app_controller"
    description = "Controls Windows applications: launch, close, focus, and list running processes."
    icon = "🖥"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._psutil = None

    async def connect(self) -> bool:
        try:
            import psutil
            self._psutil = psutil
            self._connected = True
            self._status_message = "Ready"
            return True
        except ImportError:
            logger.warning("psutil not installed. Process listing/killing unavailable.")
            self._psutil = None
            self._connected = True
            self._status_message = "Ready (limited — install psutil for full features)"
            return True
        except Exception as e:
            logger.error(f"connect failed: {e}")
            self._connected = False
            self._status_message = f"Error: {e}"
            return False

    def _resolve_app(self, app: str) -> str:
        return KNOWN_APPS.get(app.lower().strip(), app if app.endswith(".exe") else app + ".exe")

    async def execute(self, action: str, params: dict) -> str:
        try:
            if action == "open_app":
                return self._open_app(str(params.get("app", "")))
            elif action == "close_app":
                return self._close_app(str(params.get("app", "")))
            elif action == "list_running":
                return self._list_running()
            elif action == "focus_app":
                return self._focus_app(str(params.get("app", "")))
            elif action == "kill_process":
                return self._kill_process(str(params.get("name", "")))
            elif action == "get_window_title":
                return self._get_window_title()
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.error(f"execute({action}) error: {e}")
            return f"Error executing {action}: {e}"

    def _open_app(self, app: str) -> str:
        if not app:
            return "No app specified."
        exe = self._resolve_app(app)
        try:
            subprocess.Popen([exe], shell=True)
            return f"Launched: {exe}"
        except FileNotFoundError:
            return f"Could not find executable: {exe}"
        except Exception as e:
            return f"Failed to launch {exe}: {e}"

    def _close_app(self, app: str) -> str:
        if not app:
            return "No app specified."
        exe = self._resolve_app(app)
        proc_name = exe.lower()
        if self._psutil is None:
            try:
                subprocess.run(["taskkill", "/IM", exe, "/F"], capture_output=True)
                return f"Sent kill signal to {exe}."
            except Exception as e:
                return f"Failed to close {exe}: {e}"
        killed = []
        for proc in self._psutil.process_iter(["name", "pid"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() == proc_name:
                    proc.terminate()
                    killed.append(str(proc.info["pid"]))
            except (self._psutil.NoSuchProcess, self._psutil.AccessDenied):
                pass
        if killed:
            return f"Terminated {exe} (PIDs: {', '.join(killed)})."
        return f"No running process found matching: {exe}"

    def _list_running(self) -> str:
        if self._psutil is None:
            try:
                result = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True)
                lines = result.stdout.strip().split("\n")[:20]
                names = []
                for line in lines:
                    parts = line.strip().strip('"').split('","')
                    if parts:
                        names.append(parts[0])
                return "Running processes (first 20):\n" + "\n".join(f"  {n}" for n in names)
            except Exception as e:
                return f"Failed to list processes: {e}"
        try:
            procs = []
            seen = set()
            for proc in self._psutil.process_iter(["name", "pid", "status"]):
                try:
                    n = proc.info["name"] or ""
                    if n and n not in seen:
                        seen.add(n)
                        procs.append(n)
                except (self._psutil.NoSuchProcess, self._psutil.AccessDenied):
                    pass
            procs.sort()
            return f"Running processes ({len(procs)} unique):\n" + "\n".join(f"  {p}" for p in procs[:50])
        except Exception as e:
            return f"Failed to list processes: {e}"

    def _focus_app(self, app: str) -> str:
        if not app:
            return "No app specified."
        exe = self._resolve_app(app)
        base_name = exe.replace(".exe", "").lower()
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, None)
            found = []

            def enum_callback(hwnd, _):
                try:
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        title = buf.value.lower()
                        if base_name in title or app.lower() in title:
                            found.append(hwnd)
                except Exception:
                    pass
                return True

            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
            user32.EnumWindows(EnumWindowsProc(enum_callback), 0)

            if found:
                hwnd = found[0]
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
                return f"Focused window for: {app}"
            return f"No visible window found for: {app}. App may not be running or has no title bar."
        except Exception as e:
            return f"Failed to focus {app}: {e}"

    def _kill_process(self, name: str) -> str:
        if not name:
            return "No process name specified."
        exe = name if name.endswith(".exe") else name + ".exe"
        if self._psutil is None:
            try:
                subprocess.run(["taskkill", "/IM", exe, "/F"], capture_output=True)
                return f"Kill signal sent to {exe}."
            except Exception as e:
                return f"Failed to kill {exe}: {e}"
        killed = []
        for proc in self._psutil.process_iter(["name", "pid"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() == exe.lower():
                    proc.kill()
                    killed.append(str(proc.info["pid"]))
            except (self._psutil.NoSuchProcess, self._psutil.AccessDenied):
                pass
        if killed:
            return f"Killed {exe} (PIDs: {', '.join(killed)})."
        return f"No process found matching: {exe}"

    def _get_window_title(self) -> str:
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return "No active window title detected."
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return f"Active window: {buf.value}"
        except Exception as e:
            return f"Failed to get window title: {e}"

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "open_app", "description": "Launch an application by name or executable. Param: app (str)."},
            {"action": "close_app", "description": "Gracefully terminate an app by name. Param: app (str)."},
            {"action": "list_running", "description": "List all currently running process names."},
            {"action": "focus_app", "description": "Bring an app window to the foreground. Param: app (str)."},
            {"action": "kill_process", "description": "Force-kill a process by name. Param: name (str)."},
            {"action": "get_window_title", "description": "Return the title of the currently active window."},
        ]
