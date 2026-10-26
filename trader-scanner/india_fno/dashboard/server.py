#!/usr/bin/env python3
"""Local-only standard-library server for the India F&O signal dashboard."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = int(os.environ.get("INDIA_FNO_DASHBOARD_PORT", "8766"))

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        # Keep terminal output compact; never log uploaded CSV contents.
        print("[dashboard] " + (fmt % args))

if __name__ == "__main__":
    print("India F&O SMC Signal Desk: http://%s:%s" % (HOST, PORT))
    print("Local-only server. Press Ctrl+C to stop.")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
