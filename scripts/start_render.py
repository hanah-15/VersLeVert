"""Run the ASGI server and one Celery worker on a free Render demo instance."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def main():
    os.chdir(Path(__file__).resolve().parents[1])
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_production")
    # PostgreSQL retains proof state even when a free queue or web instance restarts.
    subprocess.run(
        [sys.executable, "manage.py", "process_pending_proofs", "--limit", "100"],
        check=True,
    )
    children = []
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    commands = [
        [
            sys.executable, "-m", "celery", "-A", "config", "worker",
            "--pool=solo", "--concurrency=1", "--loglevel=info",
            "--without-gossip", "--without-mingle",
        ],
        [
            sys.executable, "-m", "gunicorn", "config.asgi:application",
            "--worker-class", "uvicorn_worker.UvicornWorker",
            "--workers", os.getenv("WEB_CONCURRENCY", "1"),
            "--bind", "0.0.0.0:" + os.getenv("PORT", "10000"),
            "--timeout", "120", "--graceful-timeout", "30",
            "--access-logfile", "-", "--error-logfile", "-",
        ],
    ]
    code = 0
    try:
        for command in commands:
            children.append(subprocess.Popen(command, start_new_session=True))
        while not stopping:
            if any(child.poll() is not None for child in children):
                print("A hosted process exited; restarting the web/worker pair.", flush=True)
                code = 1
                break
            time.sleep(0.5)
    finally:
        for child in children:
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + 35
        for child in children:
            try:
                child.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
    return code


if __name__ == "__main__":
    sys.exit(main())
