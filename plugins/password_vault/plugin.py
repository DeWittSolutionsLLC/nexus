"""
Password Vault Plugin — Encrypted local password manager using Fernet (PBKDF2) or base64 fallback.
Vault stored at ~/NexusScripts/.vault  (encrypted JSON).
Passwords are NEVER logged. Raw plaintext only returned from get_password on explicit request.
"""

import os
import json
import base64
import logging
import secrets
import string
import hashlib
from datetime import datetime
from pathlib import Path
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.password_vault")

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    import base64 as _b64
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

VAULT_PATH = Path.home() / "NexusScripts" / ".vault"
SALT_PATH = Path.home() / "NexusScripts" / ".vault_salt"


class PasswordVaultPlugin(BasePlugin):
    name = "password_vault"
    description = "Encrypted local password manager — Fernet/PBKDF2 or base64 fallback"
    icon = "🔐"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)

    async def connect(self) -> bool:
        VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        mode = "Fernet/PBKDF2" if CRYPTO_AVAILABLE else "base64 obfuscation (install cryptography for real encryption)"
        self._connected = True
        self._status_message = f"Ready — encryption: {mode}"
        logger.info("Password vault connected (crypto=%s)", CRYPTO_AVAILABLE)
        return True

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "setup_vault", "description": "Initialize vault with a master password"},
            {"action": "add_password", "description": "Add a new service credential"},
            {"action": "get_password", "description": "Retrieve and decrypt a password"},
            {"action": "list_services", "description": "List service names (no passwords)"},
            {"action": "delete_entry", "description": "Remove a service credential"},
            {"action": "generate_password", "description": "Generate a strong random password"},
            {"action": "check_strength", "description": "Analyze a password's strength"},
        ]

    async def execute(self, action: str, params: dict) -> str:
        actions = {
            "setup_vault": self._setup_vault,
            "add_password": self._add_password,
            "get_password": self._get_password,
            "list_services": self._list_services,
            "delete_entry": self._delete_entry,
            "generate_password": self._generate_password,
            "check_strength": self._check_strength,
        }
        if action not in actions:
            return f"Unknown action: {action}. Available: {', '.join(actions)}"
        try:
            return await actions[action](params)
        except Exception as e:
            logger.error("Vault action %s failed: %s", action, e)
            return f"Error in {action}: {e}"

    # ── Crypto helpers ────────────────────────────────────────────────────────

    def _get_salt(self) -> bytes:
        if SALT_PATH.exists():
            return SALT_PATH.read_bytes()
        salt = os.urandom(16)
        SALT_PATH.write_bytes(salt)
        return salt

    def _derive_key(self, master_password: str) -> bytes:
        salt = self._get_salt()
        if CRYPTO_AVAILABLE:
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390000)
            return _b64.urlsafe_b64encode(kdf.derive(master_password.encode()))
        # Fallback: PBKDF2 via hashlib
        key_raw = hashlib.pbkdf2_hmac("sha256", master_password.encode(), salt, 390000)
        return base64.urlsafe_b64encode(key_raw)

    def _encrypt(self, plaintext: str, key: bytes) -> str:
        if CRYPTO_AVAILABLE:
            return Fernet(key).encrypt(plaintext.encode()).decode()
        # Fallback: XOR with key bytes then base64
        key_bytes = base64.urlsafe_b64decode(key)
        data = plaintext.encode()
        xored = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data))
        return base64.urlsafe_b64encode(xored).decode()

    def _decrypt(self, ciphertext: str, key: bytes) -> str:
        if CRYPTO_AVAILABLE:
            return Fernet(key).decrypt(ciphertext.encode()).decode()
        key_bytes = base64.urlsafe_b64decode(key)
        data = base64.urlsafe_b64decode(ciphertext.encode())
        return bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data)).decode()

    def _load_vault(self, key: bytes) -> dict:
        if not VAULT_PATH.exists():
            return {}
        ciphertext = VAULT_PATH.read_text(encoding="utf-8").strip()
        if not ciphertext:
            return {}
        raw = self._decrypt(ciphertext, key)
        return json.loads(raw)

    def _save_vault(self, data: dict, key: bytes):
        raw = json.dumps(data, ensure_ascii=False)
        ciphertext = self._encrypt(raw, key)
        VAULT_PATH.write_text(ciphertext, encoding="utf-8")

    def _require_master(self, params: dict) -> tuple[str, bytes] | tuple[None, None]:
        mp = params.get("master_password", "").strip()
        if not mp:
            return None, None
        return mp, self._derive_key(mp)

    # ── Actions ───────────────────────────────────────────────────────────────

    async def _setup_vault(self, params: dict) -> str:
        mp, key = self._require_master(params)
        if not mp:
            return "Required param: master_password"
        if VAULT_PATH.exists() and VAULT_PATH.stat().st_size > 0:
            return "Vault already initialized. To reset, delete ~/NexusScripts/.vault manually."
        self._save_vault({}, key)
        mode = "Fernet/PBKDF2" if CRYPTO_AVAILABLE else "base64 obfuscation (install cryptography package)"
        return f"Vault initialized at {VAULT_PATH}\nEncryption: {mode}"

    async def _add_password(self, params: dict) -> str:
        service = params.get("service", "").strip()
        username = params.get("username", "").strip()
        password = params.get("password", "").strip()
        mp, key = self._require_master(params)
        if not all([service, username, password, mp]):
            return "Required params: service, username, password, master_password"
        try:
            vault = self._load_vault(key)
        except Exception:
            return "Failed to decrypt vault — wrong master password?"
        entry_id = service.lower().replace(" ", "_")
        vault[entry_id] = {
            "id": entry_id,
            "service": service,
            "username": username,
            "password_encrypted": self._encrypt(password, key),
            "url": params.get("url", ""),
            "notes": params.get("notes", ""),
            "created": datetime.now().isoformat(),
        }
        self._save_vault(vault, key)
        logger.info("Added vault entry for service: %s", service)
        return f"Password for '{service}' saved. Username: {username}"

    async def _get_password(self, params: dict) -> str:
        service = params.get("service", "").strip()
        mp, key = self._require_master(params)
        if not service or not mp:
            return "Required params: service, master_password"
        try:
            vault = self._load_vault(key)
        except Exception:
            return "Failed to decrypt vault — wrong master password?"
        entry_id = service.lower().replace(" ", "_")
        if entry_id not in vault:
            available = ", ".join(vault.keys()) or "none"
            return f"Service '{service}' not found. Available: {available}"
        entry = vault[entry_id]
        password = self._decrypt(entry["password_encrypted"], key)
        return (f"Service:  {entry['service']}\n"
                f"Username: {entry['username']}\n"
                f"Password: {password}\n"
                f"URL:      {entry.get('url', 'N/A')}\n"
                f"Notes:    {entry.get('notes', '')}")

    async def _list_services(self, params: dict) -> str:
        mp, key = self._require_master(params)
        if not mp:
            return "Required param: master_password"
        try:
            vault = self._load_vault(key)
        except Exception:
            return "Failed to decrypt vault — wrong master password?"
        if not vault:
            return "Vault is empty. Use add_password to store credentials."
        lines = ["Stored services:"]
        for entry in vault.values():
            lines.append(f"  {entry['service']:<30} username: {entry['username']}")
        return "\n".join(lines)

    async def _delete_entry(self, params: dict) -> str:
        service = params.get("service", "").strip()
        mp, key = self._require_master(params)
        if not service or not mp:
            return "Required params: service, master_password"
        try:
            vault = self._load_vault(key)
        except Exception:
            return "Failed to decrypt vault — wrong master password?"
        entry_id = service.lower().replace(" ", "_")
        if entry_id not in vault:
            return f"Service '{service}' not found"
        del vault[entry_id]
        self._save_vault(vault, key)
        return f"Entry for '{service}' deleted from vault"

    async def _generate_password(self, params: dict) -> str:
        length = int(params.get("length", 16))
        use_symbols = str(params.get("symbols", True)).lower() not in ("false", "0", "no")
        length = max(8, min(128, length))
        alphabet = string.ascii_letters + string.digits
        if use_symbols:
            alphabet += "!@#$%^&*()-_=+[]{}|;:,.<>?"
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        strength = self._analyze_strength(password)
        return f"Generated password ({length} chars): {password}\nStrength: {strength}"

    async def _check_strength(self, params: dict) -> str:
        password = params.get("password", "")
        if not password:
            return "Required param: password"
        result = self._analyze_strength(password)
        return f"Password strength analysis:\n{result}"

    def _analyze_strength(self, password: str) -> str:
        score = 0
        feedback = []
        if len(password) >= 8:
            score += 1
        if len(password) >= 12:
            score += 1
        if len(password) >= 16:
            score += 1
        if any(c.isupper() for c in password):
            score += 1
        else:
            feedback.append("Add uppercase letters")
        if any(c.islower() for c in password):
            score += 1
        else:
            feedback.append("Add lowercase letters")
        if any(c.isdigit() for c in password):
            score += 1
        else:
            feedback.append("Add numbers")
        if any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in password):
            score += 1
        else:
            feedback.append("Add special characters")
        label = ["Very Weak", "Weak", "Fair", "Good", "Strong", "Very Strong", "Excellent", "Exceptional"]
        level = label[min(score, len(label) - 1)]
        tips = ("  Suggestions: " + "; ".join(feedback)) if feedback else "  No suggestions — looks great!"
        return f"  Score: {score}/7  |  Level: {level}\n  Length: {len(password)} chars\n{tips}"
