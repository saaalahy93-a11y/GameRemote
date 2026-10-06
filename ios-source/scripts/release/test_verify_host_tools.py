#!/usr/bin/env python3
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from verify_host_tools import executable, verify


class HostToolsTests(unittest.TestCase):
    def test_rejects_relative_tool_selection(self):
        with self.assertRaisesRegex(ValueError, 'absolute path'):
            executable('python3')

    def test_rejects_missing_tool(self):
        with self.assertRaisesRegex(ValueError, 'executable'):
            executable('/missing/chiaki-host-tool')

    def test_rejects_unexpected_compiler_before_generation(self):
        with patch('verify_host_tools.subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'libprotoc 33.4\n')) as run:
            with self.assertRaisesRegex(ValueError, 'Expected protoc 29.6'):
                verify(sys.executable, sys.executable)
            self.assertEqual(run.call_count, 1)

    def test_rejects_older_python_runtime_before_generation(self):
        responses = [subprocess.CompletedProcess([], 0, 'libprotoc 29.6\n'),
                     subprocess.CompletedProcess([], 0, json.dumps('5.28.3'))]
        with patch('verify_host_tools.subprocess.run', side_effect=responses) as run:
            with self.assertRaisesRegex(ValueError, 'Expected Python google.protobuf 5.29.6'):
                verify(sys.executable, sys.executable)
            self.assertEqual(run.call_count, 2)

    def test_rejects_missing_runtime_module(self):
        responses = [subprocess.CompletedProcess([], 0, 'libprotoc 29.6\n'),
                     subprocess.CalledProcessError(1, 'runtime import')]
        with patch('verify_host_tools.subprocess.run', side_effect=responses), self.assertRaises(subprocess.CalledProcessError):
            verify(sys.executable, sys.executable)


if __name__ == '__main__':
    unittest.main()
