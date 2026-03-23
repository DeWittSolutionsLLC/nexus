"""
File Manager Plugin — Local file operations. No browser needed.
"""

import os
import shutil
import logging
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.file_manager")

FILE_CATEGORIES = {
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx", ".csv", ".pptx"},
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff"},
    "Videos": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"},
    "Audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
    "Code": {".py", ".js", ".ts", ".html", ".css", ".java", ".cpp", ".c", ".go", ".rs", ".rb", ".json"},
    "Executables": {".exe", ".msi", ".bat", ".sh", ".cmd"},
}


class FileManagerPlugin(BasePlugin):
    name = "file_manager"
    description = "Search, organize, and manage local files and folders"
    icon = "📁"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)

    async def connect(self) -> bool:
        self._connected = True
        self._status_message = "Ready"
        return True

    async def execute(self, action: str, params: dict) -> str:
        actions = {
            "search_files": self._search_files,
            "organize": self._organize_folder,
            "list_directory": self._list_directory,
            "get_info": self._get_file_info,
            "move_file": self._move_file,
            "find_duplicates": self._find_duplicates,
            "disk_usage": self._disk_usage,
        }
        handler = actions.get(action)
        if not handler:
            return f"Unknown file action: {action}"
        return await handler(params)

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "search_files", "description": "Search for files by name or extension", "params": ["path", "pattern", "extension"]},
            {"action": "organize", "description": "Organize folder contents into subfolders by type", "params": ["path", "dry_run"]},
            {"action": "list_directory", "description": "List contents of a directory", "params": ["path", "show_hidden"]},
            {"action": "get_info", "description": "Get detailed info about a file or folder", "params": ["path"]},
            {"action": "move_file", "description": "Move or rename a file or folder", "params": ["source", "destination"]},
            {"action": "find_duplicates", "description": "Find duplicate files by size", "params": ["path"]},
            {"action": "disk_usage", "description": "Show disk usage breakdown by file type", "params": ["path"]},
        ]

    async def _search_files(self, params: dict) -> str:
        search_path = Path(params.get("path", os.path.expanduser("~")))
        pattern = params.get("pattern", "*")
        extension = params.get("extension", "")

        if extension:
            pattern = f"*{extension}" if extension.startswith(".") else f"*.{extension}"
        if not search_path.exists():
            return f"❌ Path not found: {search_path}"

        results = []
        try:
            for match in search_path.rglob(pattern):
                if len(results) >= 50:
                    break
                results.append(str(match))
        except PermissionError:
            pass

        if not results:
            return f"No files matching '{pattern}' in {search_path}"

        lines = [f"  📄 {r}" for r in results[:25]]
        extra = f"\n  ... and {len(results) - 25} more" if len(results) > 25 else ""
        return f"🔍 Found {len(results)} files:\n\n" + "\n".join(lines) + extra

    async def _organize_folder(self, params: dict) -> str:
        folder = Path(params.get("path", ""))
        dry_run = str(params.get("dry_run", "true")).lower() == "true"

        if not folder.exists() or not folder.is_dir():
            return f"❌ Invalid folder: {folder}"

        moves = defaultdict(list)
        for item in folder.iterdir():
            if item.is_file():
                ext = item.suffix.lower()
                category = "Other"
                for cat, extensions in FILE_CATEGORIES.items():
                    if ext in extensions:
                        category = cat
                        break
                moves[category].append(item)

        if not moves:
            return "📁 Nothing to organize — folder has no loose files."

        lines = []
        total = 0
        for category, files in sorted(moves.items()):
            lines.append(f"\n📂 {category}/")
            for f in files[:5]:
                lines.append(f"    ← {f.name}")
            if len(files) > 5:
                lines.append(f"    ... +{len(files) - 5} more")
            total += len(files)

            if not dry_run:
                dest = folder / category
                dest.mkdir(exist_ok=True)
                for f in files:
                    shutil.move(str(f), str(dest / f.name))

        label = "Would move" if dry_run else "Moved"
        note = "\n\n💡 Say 'organize with dry_run false' to actually move files." if dry_run else ""
        return f"📁 {label} {total} files into {len(moves)} categories:" + "\n".join(lines) + note

    async def _list_directory(self, params: dict) -> str:
        path = Path(params.get("path", os.path.expanduser("~")))
        show_hidden = str(params.get("show_hidden", "false")).lower() == "true"

        if not path.exists():
            return f"❌ Path not found: {path}"

        items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        lines = []
        for item in items:
            if not show_hidden and item.name.startswith("."):
                continue
            icon = "📂" if item.is_dir() else "📄"
            size = f" ({self._human_size(item.stat().st_size)})" if item.is_file() else ""
            lines.append(f"  {icon} {item.name}{size}")

        return f"📁 {path}:\n\n" + "\n".join(lines[:40])

    async def _get_file_info(self, params: dict) -> str:
        path = Path(params.get("path", ""))
        if not path.exists():
            return f"❌ Not found: {path}"
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        return (
            f"📄 {path.name}\n"
            f"  Path: {path.absolute()}\n"
            f"  Type: {'Directory' if path.is_dir() else path.suffix or 'File'}\n"
            f"  Size: {self._human_size(stat.st_size)}\n"
            f"  Modified: {modified}"
        )

    async def _move_file(self, params: dict) -> str:
        source = Path(params.get("source", ""))
        dest = Path(params.get("destination", ""))
        if not source.exists():
            return f"❌ Source not found: {source}"
        shutil.move(str(source), str(dest))
        return f"✅ Moved {source.name} → {dest}"

    async def _find_duplicates(self, params: dict) -> str:
        path = Path(params.get("path", ""))
        if not path.exists():
            return f"❌ Path not found"
        size_map = defaultdict(list)
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    size_map[f.stat().st_size].append(f)
                except OSError:
                    pass
        dupes = {s: fs for s, fs in size_map.items() if len(fs) > 1 and s > 1024}
        if not dupes:
            return "✅ No duplicates found."
        lines = []
        for size, files in sorted(dupes.items(), key=lambda x: -x[0])[:10]:
            lines.append(f"\n  Size: {self._human_size(size)}")
            for f in files[:4]:
                lines.append(f"    📄 {f}")
        return "🔍 Potential duplicates:" + "\n".join(lines)

    async def _disk_usage(self, params: dict) -> str:
        path = Path(params.get("path", os.path.expanduser("~")))
        total_size = 0
        cat_sizes = defaultdict(int)
        count = 0
        try:
            for f in path.rglob("*"):
                if f.is_file():
                    try:
                        s = f.stat().st_size
                        total_size += s
                        count += 1
                        ext = f.suffix.lower()
                        matched = False
                        for cat, exts in FILE_CATEGORIES.items():
                            if ext in exts:
                                cat_sizes[cat] += s
                                matched = True
                                break
                        if not matched:
                            cat_sizes["Other"] += s
                    except OSError:
                        pass
        except PermissionError:
            pass

        lines = [f"💾 {path}:", f"  Total: {self._human_size(total_size)} ({count} files)\n"]
        for cat, size in sorted(cat_sizes.items(), key=lambda x: -x[1]):
            pct = (size / total_size * 100) if total_size else 0
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            lines.append(f"  {cat:12s} {bar} {pct:5.1f}% ({self._human_size(size)})")
        return "\n".join(lines)

    @staticmethod
    def _human_size(size: int) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
