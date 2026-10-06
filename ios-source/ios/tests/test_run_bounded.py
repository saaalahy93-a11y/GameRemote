"""Behavioural checks for the CI deadline: preserve failures and stop child groups."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

RUNNER = Path(__file__).resolve().parents[1] / "scripts/run-bounded.py"


class DeadlineTests(unittest.TestCase):
    def run_command(self, directory, source, *options):
        return subprocess.run([sys.executable, str(RUNNER), "--log", str(Path(directory) / "command.log"),
                               *options, "--", sys.executable, "-u", "-c", source],
                              capture_output=True, text=True, timeout=10)

    def test_success_and_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_command(directory, "print('finished'); raise SystemExit(7)")
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertEqual(result.stdout, "finished\n")
            self.assertEqual((Path(directory) / "command.log").read_text(), "finished\n")
            self.assertEqual(self.run_command(directory, "print('success')").returncode, 0)

    def test_silent_child_group_is_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "escaped"
            child = f"import time,signal; from pathlib import Path; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(2); Path({str(marker)!r}).touch()"
            source = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(20)"
            result = self.run_command(directory, source, "--stall", "0.2", "--limit", "5")
            self.assertEqual(result.returncode, 124, result.stderr)
            self.assertIn("no command output", result.stderr)
            # Give an escaped child time to create the marker; a killed group cannot.
            time.sleep(1.2)
            self.assertFalse(marker.exists())

    def test_total_deadline_is_not_reset_by_output(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_command(directory, "import time\nwhile True: print('working'); time.sleep(0.05)",
                                      "--stall", "3", "--limit", "0.3")
            self.assertEqual(result.returncode, 124, result.stderr)
            self.assertIn("total deadline", result.stderr)

    def test_console_backpressure_cannot_disable_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "command.log"
            source = "import sys,time; sys.stdout.write('x'*1048576); sys.stdout.flush(); time.sleep(20)"
            process = subprocess.Popen([sys.executable, str(RUNNER), "--log", str(log),
                                        "--stall", "3", "--limit", "0.3", "--",
                                        sys.executable, "-u", "-c", source], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                # Deliberately do not consume stdout before exit: the pipe will fill.
                self.assertEqual(process.wait(timeout=4), 124)
                self.assertTrue(log.read_text().startswith("x" * 1048576))
            finally:
                if process.poll() is None:
                    # Let the wrapper's signal handler stop its command group too.
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                process.communicate(timeout=4)


if __name__ == "__main__":
    unittest.main()
