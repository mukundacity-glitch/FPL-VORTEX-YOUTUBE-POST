from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from day3.live_evidence import SourceChanged
from day3.verify_evidence import verify_with_recovery


class RenderRecoveryTests(TestCase):
    def test_changed_evidence_rerenders_cleanly_and_verifies_same_target(self):
        root = Path("/runner/day3")
        target = (11, "2026-11-21T11:00:00Z")
        verify = Mock(side_effect=[SourceChanged("changed", target), None])
        rerender = Mock()
        with patch("day3.verify_evidence.verify_bundle", verify):
            verify_with_recovery(root, rerender)
        self.assertEqual(verify.call_count, 2)
        self.assertEqual(verify.call_args.kwargs["expected_target"], target)
        rerender.assert_called_once_with(target)

    def test_keeps_blocking_if_fpl_changes_again(self):
        verify = Mock(side_effect=SourceChanged("changed", (11, "2026-11-21T11:00:00Z")))
        rerender = Mock()
        with patch("day3.verify_evidence.verify_bundle", verify):
            with self.assertRaisesRegex(SourceChanged, "changed"):
                verify_with_recovery(Path("/runner/day3"), rerender)
        rerender.assert_called_once_with((11, "2026-11-21T11:00:00Z"))
        self.assertEqual(verify.call_count, 2)

    def test_integrity_failure_does_not_retry(self):
        rerender = Mock()
        with patch("day3.verify_evidence.verify_bundle", side_effect=RuntimeError("file hash changed")):
            with self.assertRaisesRegex(RuntimeError, "file hash"):
                verify_with_recovery(Path("/runner/day3"), rerender)
        rerender.assert_not_called()
