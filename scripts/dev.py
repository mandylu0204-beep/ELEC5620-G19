"""Portable supervisor: one foreground command, two loopback services, no reload child."""
import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend-port', type=int, default=8000)
    parser.add_argument('--frontend-port', type=int, default=5173)
    parser.add_argument('--stop-file', type=Path, help='Optional cooperative stop marker for automated deployment checks.')
    args = parser.parse_args()
    if args.stop_file and args.stop_file.exists():
        parser.error('The stop marker already exists; use a fresh marker path.')
    ports = [args.backend_port, args.frontend_port]
    if len(set(ports)) != 2 or any(not 1 <= port <= 65535 for port in ports):
        parser.error('Use two distinct ports between 1 and 65535.')
    for port in ports:
        try:
            with socket.socket() as probe:
                if os.name != 'nt':
                    # Match the servers' POSIX restart behavior after TIME_WAIT.
                    # An active listener still prevents binding this port.
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(('127.0.0.1', port))
        except OSError:
            print(f'Port {port} is occupied. Choose another port; no existing process was stopped.', file=sys.stderr)
            return 1
    vite = ROOT / 'frontend/node_modules/vite/bin/vite.js'
    node = shutil.which('node')
    if node is None or not vite.is_file():
        print('Node.js or frontend dependencies missing. Run setup first.', file=sys.stderr)
        return 1
    env = os.environ.copy()
    env['CAMPMATE_BACKEND_URL'] = f'http://127.0.0.1:{args.backend_port}'
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    children: list[subprocess.Popen] = []
    try:
        children.append(subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(args.backend_port)],
            cwd=ROOT / 'backend', env=env, creationflags=flags,
        ))
        children.append(subprocess.Popen(
            [node, str(vite), '--host', '127.0.0.1', '--port', str(args.frontend_port), '--strictPort'],
            cwd=ROOT / 'frontend', env=env, creationflags=flags,
        ))
        print(f'CampMate: http://127.0.0.1:{args.frontend_port} | API: http://127.0.0.1:{args.backend_port}/docs', flush=True)
        print('Press Ctrl+C to stop both services. Restart after backend edits.', flush=True)
        while all(child.poll() is None for child in children):
            if args.stop_file and args.stop_file.exists():
                return 0
            time.sleep(0.3)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    raise SystemExit(main())
