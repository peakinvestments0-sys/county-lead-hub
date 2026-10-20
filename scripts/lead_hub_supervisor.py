"""Keep the local Lead Hub server running independently of terminal windows."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import socket
import os
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def server_is_listening():
    try:
        with socket.create_connection(("127.0.0.1", 8505), timeout=1):
            return True
    except OSError:
        return False


def main():
    # Prevent two launchers from spawning competing servers on Windows.
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    mutex = kernel.CreateMutexW(None, False, "Local\\FloridaLeadHubSupervisor")
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(mutex)
        return
    (ROOT / "data").mkdir(exist_ok=True)
    handler = RotatingFileHandler(ROOT / "data" / "lead_hub_supervisor.log", maxBytes=1_000_000, backupCount=2)
    logging.basicConfig(handlers=[handler], level=logging.INFO, format="%(asctime)s %(message)s")
    python = Path(sys.executable).with_name("python.exe")
    child = None
    watcher = None
    retry_watcher_at = 0
    try:
        while True:
            if child is not None and child.poll() is not None:
                logging.warning("Lead Hub exited with code %s; restarting", child.returncode)
                child = None
            if child is None and not server_is_listening():
                logging.info("Starting Lead Hub on port 8505")
                # No terminal parent; Task Scheduler owns this supervisor.
                with (ROOT / "data" / "lead_hub_server.log").open("w", encoding="utf-8") as output:
                    child = subprocess.Popen(
                        [str(python), "-u", str(ROOT / "server.py"), "--no-browser"],
                        cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
            if watcher is not None and watcher.poll() is not None:
                logging.warning('Inbound watcher exited with code %s; retrying in 30s', watcher.returncode)
                watcher = None
                retry_watcher_at = time.monotonic() + 30
            if watcher is None and time.monotonic() >= retry_watcher_at:
                node = shutil.which('node')
                if node:
                    logging.info('Starting inbound pull watcher')
                    with (ROOT / 'data' / 'inbound_watcher.log').open('a', encoding='utf-8') as output:
                        watcher = subprocess.Popen(
                            [node, f'--env-file-if-exists={ROOT / ".env"}', str(ROOT / 'scripts' / 'inbound-watcher.js')],
                            cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                            env={**os.environ, 'INBOUND_PYTHON': str(python), 'INBOUND_PARENT_PID': str(os.getpid())},
                            creationflags=subprocess.CREATE_NO_WINDOW,
                        )
                else:
                    logging.error('Inbound watcher requires Node.js >=22.9 on PATH')
                    retry_watcher_at = time.monotonic() + 30
            time.sleep(3)
    finally:
        # The watcher notices this PID's exit and drains an active import before
        # stopping. terminate() on Windows would interrupt that import outright.
        kernel.CloseHandle(mutex)


if __name__ == "__main__":
    main()
