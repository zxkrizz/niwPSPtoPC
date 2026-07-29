from __future__ import annotations

import os
import unittest
import uuid

from pc_server.single_instance import SingleInstance


@unittest.skipUnless(os.name == "nt", "Windows named mutex test")
class SingleInstanceTests(unittest.TestCase):
    def test_second_guard_detects_existing_instance(self) -> None:
        name = f"Local\\niwPSPtoPC.test.{uuid.uuid4()}"

        with SingleInstance(name) as first:
            with SingleInstance(name) as second:
                self.assertTrue(first.acquired)
                self.assertFalse(second.acquired)


if __name__ == "__main__":
    unittest.main()
