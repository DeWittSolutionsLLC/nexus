from core.plugin_manager import BasePlugin
import logging, json
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("nexus.plugins.qr_generator")

QR_DIR = Path.home() / "NexusScripts" / "qr_codes"

try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

try:
    from pyzbar import pyzbar
    from PIL import Image as PilImage
    HAS_PYZBAR = True
except ImportError:
    HAS_PYZBAR = False

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


def _require_qrcode():
    if not HAS_QRCODE:
        return "qrcode library not installed. Run: pip install qrcode[pil]"
    return None


def _make_qr(data: str, filename: str, size: int = 10) -> str:
    err = _require_qrcode()
    if err:
        return err
    QR_DIR.mkdir(parents=True, exist_ok=True)
    qr = qrcode.QRCode(version=1, box_size=size, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    path = QR_DIR / filename
    img.save(str(path))
    return str(path)


class QrGeneratorPlugin(BasePlugin):
    name = "qr_generator"
    description = "Generate and read QR codes for URLs, text, WiFi, and contacts."
    icon = "⬛"

    async def connect(self) -> bool:
        QR_DIR.mkdir(parents=True, exist_ok=True)
        self._connected = True
        libs = []
        if HAS_QRCODE:
            libs.append("qrcode")
        if HAS_PYZBAR:
            libs.append("pyzbar")
        if HAS_CV2:
            libs.append("cv2")
        self._status_message = f"Ready (libs: {', '.join(libs) or 'none — install qrcode[pil]'})"
        return True

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "generate", "description": "Generate a QR code from any text or URL", "params": ["data", "filename", "size"]},
            {"action": "generate_wifi", "description": "Generate a WiFi QR code", "params": ["ssid", "password", "security"]},
            {"action": "generate_contact", "description": "Generate a vCard contact QR code", "params": ["name", "phone", "email"]},
            {"action": "generate_url", "description": "Generate a URL QR code", "params": ["url", "filename"]},
            {"action": "list_qr_codes", "description": "List all generated QR code files", "params": []},
            {"action": "read_qr", "description": "Decode a QR code from an image file", "params": ["image_path"]},
        ]

    async def execute(self, action: str, params: dict) -> str:
        try:
            if action == "generate":
                return await self._generate(params)
            elif action == "generate_wifi":
                return await self._generate_wifi(params)
            elif action == "generate_contact":
                return await self._generate_contact(params)
            elif action == "generate_url":
                return await self._generate_url(params)
            elif action == "list_qr_codes":
                return await self._list_qr_codes(params)
            elif action == "read_qr":
                return await self._read_qr(params)
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.exception("QrGenerator error")
            return f"Error in qr_generator.{action}: {e}"

    async def _generate(self, params: dict) -> str:
        data = params.get("data", "").strip()
        if not data:
            return "No data provided."
        size = int(params.get("size", 10))
        filename = params.get("filename", "").strip()
        if not filename:
            safe = "".join(c if c.isalnum() else "_" for c in data[:30])
            filename = f"qr_{safe}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        if not filename.endswith(".png"):
            filename += ".png"
        result = _make_qr(data, filename, size)
        if result.startswith("/") or result[1:3] == ":\\":
            return f"QR code generated: {result}"
        return result

    async def _generate_wifi(self, params: dict) -> str:
        ssid = params.get("ssid", "").strip()
        password = params.get("password", "").strip()
        security = params.get("security", "WPA").strip().upper()
        if not ssid:
            return "SSID is required."
        wifi_data = f"WIFI:T:{security};S:{ssid};P:{password};;"
        safe_ssid = "".join(c if c.isalnum() else "_" for c in ssid)
        filename = f"wifi_{safe_ssid}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        result = _make_qr(wifi_data, filename)
        if result.startswith("/") or (len(result) > 1 and result[1] == ":"):
            return f"WiFi QR code generated for '{ssid}': {result}"
        return result

    async def _generate_contact(self, params: dict) -> str:
        name = params.get("name", "").strip()
        phone = params.get("phone", "").strip()
        email = params.get("email", "").strip()
        if not name:
            return "Name is required."
        vcard = (
            f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\n"
            f"TEL:{phone}\n"
            f"EMAIL:{email}\n"
            f"END:VCARD"
        )
        safe_name = "".join(c if c.isalnum() else "_" for c in name)
        filename = f"contact_{safe_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        result = _make_qr(vcard, filename)
        if result.startswith("/") or (len(result) > 1 and result[1] == ":"):
            return f"Contact QR code generated for '{name}': {result}"
        return result

    async def _generate_url(self, params: dict) -> str:
        url = params.get("url", "").strip()
        if not url:
            return "No URL provided."
        filename = params.get("filename", "").strip()
        if not filename:
            domain = url.replace("https://", "").replace("http://", "").split("/")[0]
            safe = "".join(c if c.isalnum() else "_" for c in domain)
            filename = f"url_{safe}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        if not filename.endswith(".png"):
            filename += ".png"
        result = _make_qr(url, filename)
        if result.startswith("/") or (len(result) > 1 and result[1] == ":"):
            return f"URL QR code generated: {result}"
        return result

    async def _list_qr_codes(self, params: dict) -> str:
        QR_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(QR_DIR.glob("*.png"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            return f"No QR codes found in {QR_DIR}"
        lines = [f"QR Codes in {QR_DIR} ({len(files)} files):"]
        for f in files:
            size_kb = f.stat().st_size // 1024
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            lines.append(f"  {f.name} ({size_kb}KB, {mtime})")
        return "\n".join(lines)

    async def _read_qr(self, params: dict) -> str:
        image_path = params.get("image_path", "").strip()
        if not image_path:
            return "No image path provided."
        path = Path(image_path)
        if not path.exists():
            return f"File not found: {image_path}"

        if HAS_PYZBAR:
            try:
                img = PilImage.open(str(path))
                decoded = pyzbar.decode(img)
                if decoded:
                    results = [d.data.decode("utf-8") for d in decoded]
                    return f"QR code decoded ({len(results)} code(s)):\n" + "\n".join(f"  {r}" for r in results)
                return "No QR code detected in image (pyzbar)."
            except Exception as e:
                logger.warning(f"pyzbar failed: {e}")

        if HAS_CV2:
            try:
                img = cv2.imread(str(path))
                detector = cv2.QRCodeDetector()
                data, _, _ = detector.detectAndDecode(img)
                if data:
                    return f"QR code decoded (cv2): {data}"
                return "No QR code detected in image (cv2)."
            except Exception as e:
                logger.warning(f"cv2 failed: {e}")

        return "No QR reader available. Install: pip install pyzbar pillow  OR  pip install opencv-python"
