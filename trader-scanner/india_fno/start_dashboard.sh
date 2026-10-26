#!/data/data/com.termux/files/usr/bin/sh
set -eu
cd "$(dirname "$0")/dashboard"
exec python server.py
