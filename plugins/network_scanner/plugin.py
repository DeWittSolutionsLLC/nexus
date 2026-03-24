"""
Network Scanner Plugin — Scans local network, checks ports, pings hosts, and measures connectivity.
Uses socket, subprocess, platform, threading, and optionally requests.
"""

import socket
import subprocess
import platform
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.plugin_manager import BasePlugin

logger = logging.getLogger("nexus.plugins.network_scanner")


class NetworkScannerPlugin(BasePlugin):
    name = "network_scanner"
    description = "Scans local network, checks ports, pings hosts, monitors connectivity"
    icon = "🌐"

    def __init__(self, config: dict, browser_engine=None):
        super().__init__(config, browser_engine)
        self._requests_available = False

    async def connect(self) -> bool:
        try:
            import requests  # noqa: F401
            self._requests_available = True
        except ImportError:
            logger.warning("requests not installed — some actions will be limited")
        self._connected = True
        self._status_message = "Ready"
        return True

    def get_capabilities(self) -> list[dict]:
        return [
            {"action": "get_my_ip", "description": "Get local and public IP addresses"},
            {"action": "scan_network", "description": "Ping-scan a subnet for alive hosts"},
            {"action": "check_port", "description": "Test if a TCP port is open on a host"},
            {"action": "ping_host", "description": "Ping a host and return latency in ms"},
            {"action": "check_internet", "description": "Verify internet connectivity"},
            {"action": "get_network_info", "description": "Get local hostname, IPs, and gateway attempt"},
            {"action": "port_scan", "description": "Check multiple ports on a host"},
            {"action": "speed_test_simple", "description": "Estimate download speed from a known URL"},
        ]

    async def execute(self, action: str, params: dict) -> str:
        actions = {
            "get_my_ip": self._get_my_ip,
            "scan_network": self._scan_network,
            "check_port": self._check_port,
            "ping_host": self._ping_host,
            "check_internet": self._check_internet,
            "get_network_info": self._get_network_info,
            "port_scan": self._port_scan,
            "speed_test_simple": self._speed_test_simple,
        }
        if action not in actions:
            return f"Unknown action: {action}. Available: {', '.join(actions)}"
        try:
            return await actions[action](params)
        except Exception as e:
            logger.error("Action %s failed: %s", action, e)
            return f"Error in {action}: {e}"

    async def _get_my_ip(self, params: dict) -> str:
        local_ip = "unknown"
        public_ip = "unknown"
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            pass
        if self._requests_available:
            try:
                import requests
                resp = requests.get("https://api.ipify.org", timeout=5)
                public_ip = resp.text.strip()
            except Exception:
                pass
        return f"Local IP:  {local_ip}\nPublic IP: {public_ip}"

    def _ping_one(self, host: str) -> bool:
        param = "-n" if platform.system().lower() == "windows" else "-c"
        try:
            result = subprocess.run(
                ["ping", param, "1", "-w", "500", host],
                capture_output=True, timeout=3
            )
            return result.returncode == 0
        except Exception:
            return False

    async def _scan_network(self, params: dict) -> str:
        subnet = params.get("subnet", "192.168.1")
        alive = []
        lock = threading.Lock()

        def check(i):
            host = f"{subnet}.{i}"
            if self._ping_one(host):
                with lock:
                    alive.append(host)

        with ThreadPoolExecutor(max_workers=50) as ex:
            futures = [ex.submit(check, i) for i in range(1, 255)]
            for f in as_completed(futures):
                pass

        alive.sort(key=lambda ip: int(ip.split(".")[-1]))
        if not alive:
            return f"No alive hosts found on {subnet}.0/24"
        return f"Alive hosts on {subnet}.0/24 ({len(alive)} found):\n" + "\n".join(alive)

    async def _check_port(self, params: dict) -> str:
        host = params.get("host", "")
        port = int(params.get("port", 80))
        if not host:
            return "Required param: host"
        try:
            with socket.create_connection((host, port), timeout=3):
                return f"Port {port} on {host}: OPEN"
        except (socket.timeout, ConnectionRefusedError):
            return f"Port {port} on {host}: CLOSED"
        except Exception as e:
            return f"Port {port} on {host}: ERROR — {e}"

    async def _ping_host(self, params: dict) -> str:
        host = params.get("host", "")
        if not host:
            return "Required param: host"
        param = "-n" if platform.system().lower() == "windows" else "-c"
        try:
            start = time.monotonic()
            result = subprocess.run(
                ["ping", param, "4", host],
                capture_output=True, text=True, timeout=15
            )
            elapsed_ms = (time.monotonic() - start) * 1000
            output = result.stdout.strip()
            if result.returncode == 0:
                return f"Ping {host}: reachable\nElapsed: {elapsed_ms:.0f} ms total\n{output}"
            return f"Ping {host}: unreachable\n{output}"
        except subprocess.TimeoutExpired:
            return f"Ping {host}: timed out"
        except Exception as e:
            return f"Ping {host} failed: {e}"

    async def _check_internet(self, params: dict) -> str:
        results = []
        dns_ok = self._ping_one("8.8.8.8")
        results.append(f"Google DNS (8.8.8.8): {'reachable' if dns_ok else 'unreachable'}")
        if self._requests_available:
            import requests
            for url in ["https://www.google.com", "https://www.cloudflare.com"]:
                try:
                    r = requests.get(url, timeout=5)
                    results.append(f"{url}: HTTP {r.status_code}")
                except Exception as e:
                    results.append(f"{url}: failed ({e})")
        connected = dns_ok
        summary = "Internet: CONNECTED" if connected else "Internet: OFFLINE"
        return summary + "\n" + "\n".join(results)

    async def _get_network_info(self, params: dict) -> str:
        lines = []
        try:
            hostname = socket.gethostname()
            lines.append(f"Hostname: {hostname}")
            addrs = socket.getaddrinfo(hostname, None)
            ips = list({a[4][0] for a in addrs})
            lines.append(f"Resolved IPs: {', '.join(ips)}")
        except Exception as e:
            lines.append(f"Hostname lookup failed: {e}")
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            lines.append(f"Primary local IP: {local_ip}")
        except Exception:
            pass
        return "\n".join(lines) if lines else "Could not retrieve network info"

    async def _port_scan(self, params: dict) -> str:
        host = params.get("host", "")
        ports = params.get("ports", [80, 443, 22, 3389, 8080])
        if not host:
            return "Required param: host"
        if isinstance(ports, str):
            ports = [int(p.strip()) for p in ports.split(",")]
        results = []
        for port in ports:
            try:
                with socket.create_connection((host, int(port)), timeout=2):
                    results.append(f"  Port {port:>5}: OPEN")
            except Exception:
                results.append(f"  Port {port:>5}: closed")
        return f"Port scan for {host}:\n" + "\n".join(results)

    async def _speed_test_simple(self, params: dict) -> str:
        if not self._requests_available:
            return "requests not installed — cannot run speed test"
        import requests
        test_url = "http://speed.cloudflare.com/__down?bytes=5000000"
        try:
            start = time.monotonic()
            resp = requests.get(test_url, timeout=30, stream=True)
            total = 0
            for chunk in resp.iter_content(chunk_size=65536):
                total += len(chunk)
            elapsed = time.monotonic() - start
            speed_mbps = (total * 8) / (elapsed * 1_000_000)
            return (f"Speed test complete:\n"
                    f"  Downloaded: {total / (1024*1024):.2f} MB in {elapsed:.2f} s\n"
                    f"  Speed: {speed_mbps:.2f} Mbps")
        except Exception as e:
            return f"Speed test failed: {e}"
