"""Python vs Rust port parity (skipped unless the Rust binary is built)."""
import os
import subprocess
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BINARY = os.path.join(REPO, 'rust', 'target', 'release', 'documix-rs')


@unittest.skipUnless(os.path.exists(BINARY), 'Rust port not built (cd rust && cargo build --release)')
class TestRustParity(unittest.TestCase):
    def test_outputs_match(self):
        proc = subprocess.run([sys.executable, os.path.join(REPO, 'scripts', 'parity.py'), '--rust', BINARY,
                               '--python', sys.executable], capture_output=True, text=True, cwd=REPO)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)


if __name__ == '__main__':
    unittest.main()
