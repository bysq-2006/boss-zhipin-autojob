import unittest
from _ctypes import COMError
from unittest.mock import patch

import zhipin_win


class StableSnapshotTests(unittest.TestCase):
    def test_retries_with_a_fresh_document_after_stale_uia_proxy(self):
        stale = COMError(-2147220991, "stale UIA proxy", (None, None, None, 0, None))
        expected_ctrls = [object()]
        expected_jobs = [{"i": 0, "title": "后端开发"}]

        with patch.object(zhipin_win, "find_document", side_effect=["old", "fresh"]), patch.object(
            zhipin_win,
            "snapshot_jobs",
            side_effect=[stale, (expected_ctrls, expected_jobs)],
        ), patch.object(zhipin_win.time, "sleep"):
            doc, ctrls, jobs = zhipin_win.stable_snapshot(object())

        self.assertEqual(doc, "fresh")
        self.assertIs(ctrls, expected_ctrls)
        self.assertIs(jobs, expected_jobs)

    def test_returns_empty_after_repeated_com_failures(self):
        stale = COMError(-2147220991, "stale UIA proxy", (None, None, None, 0, None))

        with patch.object(zhipin_win, "find_document", return_value="doc"), patch.object(
            zhipin_win, "snapshot_jobs", side_effect=[stale, stale, stale]
        ), patch.object(zhipin_win.time, "sleep"):
            result = zhipin_win.stable_snapshot(object())

        self.assertEqual(result, (None, [], []))


if __name__ == "__main__":
    unittest.main()
