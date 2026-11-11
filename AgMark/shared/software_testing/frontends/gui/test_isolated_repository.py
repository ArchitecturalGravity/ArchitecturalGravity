"""External fixture publication remains external under managed temp policy."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from AgMark.shared.runtime.artifacts import PublicationDestination
from AgMark.shared.software_testing.frontends.gui.isolated_repository import external_evidence_directory


class ExternalEvidenceDirectoryTests(unittest.TestCase):
    def test_managed_temp_inside_repository_uses_disposable_sibling(self):
        with tempfile.TemporaryDirectory() as outer:
            root = Path(outer) / "repository"
            managed_temp = root / "AgMark" / "Runtime" / "temp"
            managed_temp.mkdir(parents=True)
            with patch("tempfile.tempdir", str(managed_temp)):
                with external_evidence_directory(root) as name:
                    destination = Path(name)
                    self.assertEqual(destination.parent, root.parent)
                    PublicationDestination.external(destination, repository_root=root)
                self.assertFalse(destination.exists())

    def test_external_default_temp_remains_usable(self):
        with tempfile.TemporaryDirectory() as outer:
            root = Path(outer) / "repository"
            root.mkdir()
            with patch("tempfile.tempdir", str(Path(outer))):
                with external_evidence_directory(root) as name:
                    self.assertEqual(Path(name).parent, Path(outer))
                    PublicationDestination.external(Path(name), repository_root=root)
