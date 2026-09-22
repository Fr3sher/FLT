"""
SAFE ComfyUI Service
===================
✅ Flask-safe (no process scanning)
✅ PID-based restart only
✅ Windows compatible

Lifted from the parent project's app/services/comfyui_service.py for LoRA
Dataset Studio: SRC's module-level COMFYUI_API_ADDRESS constant becomes a live
`cfg.get('comfyui.api_url')` call (config.json changes take effect without a
restart). SRC's COMFYUI_BASE_DIR/COMFYUI_BATCH_FILE imports are dropped — this
app never launches or stops ComfyUI itself, so start_comfyui_process /
stop_comfyui_process were already no-ops and stay that way.

SRC's `queue_prompt` is gone too: nothing in this app ever called it, and it
submitted with no timeout at all. The one live submission path is
`app.utils.comfyui.queue_prompt_to_comfyui`, which is bounded and carries the
error contract job_queue relies on — a second, unbounded door into /prompt was
only ever a trap for the next caller.
"""
from ..timeout_settings import network_timeout

import os
import socket
import threading
import logging
import requests
from urllib.parse import urljoin
from typing import Tuple

from .. import config as cfg

logger = logging.getLogger(__name__)

COMFYUI_PID_FILE = os.path.join(os.path.dirname(__file__), "comfyui.pid")


class ComfyUIService:
    def __init__(self):
        self.api_host = "127.0.0.1"
        self.api_port = 8188
        self.startup_timeout = 60
        self.check_interval = 2
        self._startup_lock = threading.Lock()
        self._is_starting = False
        self._connection_error = 'ComfyUI is not reachable. Check its server and API URL.'

    # ---------------- API ----------------
    def parse_api_address(self):
        addr = cfg.get('comfyui.api_url').replace("http://", "").replace("https://", "").rstrip("/")
        if ':' in addr:
            self.api_host, port = addr.split(':', 1)
            self.api_port = int(port)
        else:
            self.api_host = addr
            self.api_port = 8188

    def check_connection(self) -> bool:
        self._connection_error = 'ComfyUI is not reachable. Check its server and API URL.'
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(network_timeout(2))
                if s.connect_ex((self.api_host, self.api_port)) != 0:
                    return False
            r = requests.get(urljoin(cfg.get('comfyui.api_url'), "/system_stats"), timeout=network_timeout(3))
            return r.status_code in (200, 404)
        except requests.exceptions.ReadTimeout:
            self._connection_error = (
                'ComfyUI is answering too slowly. Nothing was submitted; '
                'retry when the server responds.')
            return False
        except (socket.error, requests.RequestException, ConnectionError, OSError):
            return False

    # ---------------- PID (DEPRECATED) ----------------
    # ---------------- Lifecycle ----------------
    def start_comfyui(self) -> Tuple[bool, str]:
        """Check whether externally managed ComfyUI is reachable; do not launch processes."""
        self.parse_api_address()
        if self.check_connection():
            return True, "Running (External)"

        logger.warning("⚠️ ComfyUI is unreachable, and automatic startup is disabled.")
        return False, self._connection_error

    def ensure_comfyui_running(self) -> Tuple[bool, str]:
        """Check the connection only."""
        self.parse_api_address()
        if self.check_connection():
            return True, "Running"
        return False, self._connection_error

    # Unified public API used by queue_manager.
    def stop_comfyui_process(self):
        """Process stopping is disabled."""
        logger.warning("⚠️ stop_comfyui_process ignored.")
        return True

    def start_comfyui_process(self):
        """Process startup is disabled."""
        logger.warning("⚠️ start_comfyui_process ignored.")
        return self.check_connection()


comfyui_service = ComfyUIService()

def ensure_comfyui_before_generation():
    return comfyui_service.ensure_comfyui_running()
