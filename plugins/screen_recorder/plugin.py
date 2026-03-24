from core.plugin_manager import BasePlugin
import logging, json, threading
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("nexus.plugins.screen_recorder")

SCREENSHOTS_DIR = Path.home() / "NexusScripts" / "recordings" / "screenshots"
RECORDINGS_DIR = Path.home() / "NexusScripts" / "recordings"

try:
    import imageio
    IMAGEIO_AVAILABLE = True
except ImportError:
    IMAGEIO_AVAILABLE = False
    logger.warning("imageio not available — video recording disabled, PNG frames only.")


class ScreenRecorderPlugin(BasePlugin):
    name = "screen_recorder"
    description = "Record screen as video or capture screenshots"
    icon = "🎬"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        self._recording = False
        self._record_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._current_file: Path | None = None
        self._record_start: datetime | None = None
        self._fps = 10

    # ------------------------------------------------------------------ helpers

    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def _capture_screen(self, region: dict | None = None):
        import mss
        import mss.tools
        with mss.mss() as sct:
            monitor = region if region else sct.monitors[0]
            return sct.grab(monitor)

    def _record_loop(self, out_path: Path, fps: int) -> None:
        interval = 1.0 / fps
        if IMAGEIO_AVAILABLE:
            writer = imageio.get_writer(str(out_path), fps=fps, macro_block_size=1)
        else:
            frame_dir = out_path.with_suffix("")
            frame_dir.mkdir(parents=True, exist_ok=True)
            writer = None
        frame_idx = 0
        import mss
        import numpy as np
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            while not self._stop_event.wait(interval):
                try:
                    img = sct.grab(monitor)
                    arr = np.array(img)[:, :, :3]  # drop alpha
                    if writer:
                        writer.append_data(arr)
                    else:
                        import mss.tools
                        frame_path = frame_dir / f"frame_{frame_idx:06d}.png"
                        mss.tools.to_png(img.rgb, img.size, output=str(frame_path))
                    frame_idx += 1
                except Exception as e:
                    logger.error("Frame capture error: %s", e)
        if writer:
            try:
                writer.close()
            except Exception:
                pass
        logger.info("Recording saved: %s", out_path)

    # ------------------------------------------------------------------ actions

    def screenshot(self, params=None) -> dict:
        params = params or {}
        filename = params.get("filename") or f"screenshot_{self._timestamp()}.png"
        if not filename.endswith(".png"):
            filename += ".png"
        out_path = SCREENSHOTS_DIR / filename
        try:
            import mss
            import mss.tools
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                img = sct.grab(monitor)
                mss.tools.to_png(img.rgb, img.size, output=str(out_path))
            size_kb = round(out_path.stat().st_size / 1024, 1)
            logger.info("Screenshot saved: %s", out_path)
            return {"success": True, "path": str(out_path), "size_kb": size_kb}
        except Exception as e:
            logger.exception("Screenshot failed")
            return {"error": str(e)}

    def screenshot_region(self, params=None) -> dict:
        params = params or {}
        try:
            x = int(params.get("x", 0))
            y = int(params.get("y", 0))
            width = int(params.get("width", 800))
            height = int(params.get("height", 600))
        except (ValueError, TypeError) as e:
            return {"error": f"Invalid region parameters: {e}"}
        filename = f"region_{self._timestamp()}.png"
        out_path = SCREENSHOTS_DIR / filename
        try:
            import mss
            import mss.tools
            region = {"left": x, "top": y, "width": width, "height": height}
            with mss.mss() as sct:
                img = sct.grab(region)
                mss.tools.to_png(img.rgb, img.size, output=str(out_path))
            size_kb = round(out_path.stat().st_size / 1024, 1)
            return {"success": True, "path": str(out_path), "size_kb": size_kb, "region": region}
        except Exception as e:
            logger.exception("Region screenshot failed")
            return {"error": str(e)}

    def start_recording(self, params=None) -> dict:
        params = params or {}
        if self._recording:
            return {"error": "Recording already active. Stop it first."}
        fps = int(params.get("fps", 10))
        filename = params.get("filename") or f"recording_{self._timestamp()}"
        ext = ".mp4" if IMAGEIO_AVAILABLE else "_frames"
        out_path = RECORDINGS_DIR / (filename if filename.endswith((".mp4", ".avi")) else filename + ext)
        self._stop_event.clear()
        self._fps = fps
        self._current_file = out_path
        self._record_start = datetime.now()
        self._recording = True
        self._record_thread = threading.Thread(
            target=self._record_loop, args=(out_path, fps), daemon=True
        )
        self._record_thread.start()
        logger.info("Recording started: %s at %d fps", out_path, fps)
        return {"success": True, "message": f"Recording started.", "file": str(out_path), "fps": fps}

    def stop_recording(self, params=None) -> dict:
        if not self._recording:
            return {"error": "No active recording."}
        self._stop_event.set()
        if self._record_thread:
            self._record_thread.join(timeout=10)
        self._recording = False
        duration = None
        size_kb = None
        if self._record_start:
            duration = round((datetime.now() - self._record_start).total_seconds(), 1)
        if self._current_file and self._current_file.exists():
            size_kb = round(self._current_file.stat().st_size / 1024, 1)
        result = {
            "success": True,
            "message": "Recording stopped.",
            "file": str(self._current_file),
            "duration_seconds": duration,
            "size_kb": size_kb,
        }
        self._current_file = None
        self._record_start = None
        return result

    def get_recording_status(self, params=None) -> dict:
        duration = None
        size_kb = None
        if self._recording and self._record_start:
            duration = round((datetime.now() - self._record_start).total_seconds(), 1)
        if self._current_file and self._current_file.exists():
            size_kb = round(self._current_file.stat().st_size / 1024, 1)
        return {
            "recording": self._recording,
            "file": str(self._current_file) if self._current_file else None,
            "duration_seconds": duration,
            "size_kb": size_kb,
            "fps": self._fps if self._recording else None,
        }

    def list_recordings(self, params=None) -> dict:
        recordings = []
        for p in sorted(RECORDINGS_DIR.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True):
            if p.is_file() and p.suffix in (".mp4", ".avi", ".mkv"):
                stat = p.stat()
                recordings.append({
                    "filename": p.name,
                    "path": str(p),
                    "size_kb": round(stat.st_size / 1024, 1),
                    "created": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
                })
        screenshots = []
        for p in sorted(SCREENSHOTS_DIR.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True):
            if p.is_file() and p.suffix == ".png":
                stat = p.stat()
                screenshots.append({
                    "filename": p.name,
                    "path": str(p),
                    "size_kb": round(stat.st_size / 1024, 1),
                    "created": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
                })
        return {"recordings": recordings, "screenshots": screenshots}

    def delete_recording(self, params=None) -> dict:
        params = params or {}
        filename = params.get("filename", "").strip()
        if not filename:
            return {"error": "filename is required."}
        for search_dir in [RECORDINGS_DIR, SCREENSHOTS_DIR]:
            target = search_dir / filename
            if target.exists() and target.is_file():
                target.unlink()
                return {"success": True, "message": f"Deleted {filename}."}
        return {"error": f"File '{filename}' not found in recordings or screenshots."}

    async def execute(self, action: str, params: dict) -> str:
        if params is None:
            params = {}
        actions = {
            "screenshot": self.screenshot,
            "screenshot_region": self.screenshot_region,
            "start_recording": self.start_recording,
            "stop_recording": self.stop_recording,
            "get_recording_status": self.get_recording_status,
            "list_recordings": self.list_recordings,
            "delete_recording": self.delete_recording,
        }
        if action not in actions:
            return f"Unknown action '{action}'. Available: {list(actions.keys())}"
        try:
            result = actions[action](params)
            return result if isinstance(result, str) else str(result)
        except Exception as e:
            logger.exception("Error in action '%s'", action)
            return f"Error: {e}"

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "screenshot",         "description": "Capture full screen as PNG"},
            {"action": "screenshot_region",  "description": "Capture a specific screen region"},
            {"action": "start_recording",    "description": "Start screen video recording"},
            {"action": "stop_recording",     "description": "Stop screen recording and save file"},
            {"action": "get_recording_status","description": "Check if recording is active and duration"},
            {"action": "list_recordings",    "description": "List all saved recordings and screenshots"},
            {"action": "delete_recording",   "description": "Delete a recording file"},
        ]

    def shutdown(self) -> None:
        if self._recording:
            self.stop_recording()
