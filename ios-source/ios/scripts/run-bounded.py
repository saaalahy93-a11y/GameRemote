#!/usr/bin/env python3
"""Run one CI command, retain its log and stop its process group on a deadline.

No retries or background service. Diagnostics add no process arguments or
environment variables; the command's own output is retained unchanged.
"""
import argparse
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def stop_group(process):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        # Reap an exited leader before addressing the group again. On macOS a
        # zombie-only group may reject SIGKILL with EPERM rather than ESRCH.
        process.poll()
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            break
        if sig == signal.SIGTERM:
            time.sleep(1)
    process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stall", type=float, default=300)
    parser.add_argument("--limit", type=float, default=1200)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or any(not math.isfinite(value) or value <= 0 for value in (args.stall, args.limit)):
        parser.error("a command and positive deadlines are required")
    args.log.parent.mkdir(parents=True, exist_ok=True)
    started = changed = heartbeat = time.monotonic()
    size = 0
    reason = None
    with args.log.open("wb") as output, args.log.open("rb") as reader:
        try:
            process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as error:
            print(f"Could not launch command: {error.strerror}", file=sys.stderr)
            return 127

        def interrupted(signum, _frame):
            raise InterruptedError(signum)

        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, interrupted)
        # A stuck log consumer must not disable the command's deadline. Console
        # forwarding is best effort; the complete output always stays in the file.
        stdout = sys.stdout.fileno()
        was_blocking = os.get_blocking(stdout)
        os.set_blocking(stdout, False)

        def forward(data):
            try:
                os.write(stdout, data)
            except (BlockingIOError, BrokenPipeError):
                pass

        try:
            while True:
                data = reader.read(65536)
                if data:
                    forward(data)
                if process.poll() is not None:
                    # Drain in bounded chunks; console backpressure cannot stall it.
                    while data := reader.read(65536):
                        forward(data)
                    return process.returncode if process.returncode >= 0 else 128 - process.returncode
                now = time.monotonic()
                current = args.log.stat().st_size
                if current != size:
                    size, changed = current, now
                if now - started >= args.limit:
                    reason = f"total deadline ({args.limit:g}s)"
                elif now - changed >= args.stall:
                    reason = f"no command output for {args.stall:g}s"
                if reason:
                    break
                if now - heartbeat >= 60:
                    forward(f"Build command still running: {int(now - started)}s; saved {size} log bytes\n".encode())
                    heartbeat = now
                time.sleep(0.1)
        except InterruptedError as error:
            reason = f"interrupted by signal {error.args[0]}"
        finally:
            os.set_blocking(stdout, was_blocking)
            if process.poll() is None or reason:
                stop_group(process)
        message = f"Command stopped: {reason}. Full output: {args.log}\n"
        output.write(message.encode())
        print(message, file=sys.stderr, end="")
        return 124


if __name__ == "__main__":
    sys.exit(main())
