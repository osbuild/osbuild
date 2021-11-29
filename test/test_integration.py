#!/usr/bin/python3

import subprocess
import unittest

class TestIntegration(unittest.TestCase):
    def test_assertMac(self):
        temp = subprocess.run(['osbuild', 'data/manifests/fedora-test-label-mac.json', '--output-directory=/tmp'],
        capture_output=True, check=True)
        val = temp.returncode
        self.assertEqual(val, 0)

    def test_assertNoMac(self):
        temp = subprocess.run(['osbuild', 'data/manifests/fedora-test-label.json', '--output-directory=/tmp'],
        capture_output=True, check=True)
        val = temp.returncode
        self.assertEqual(val, 0)

if __name__ == '__main__' :
    unittest.main()
