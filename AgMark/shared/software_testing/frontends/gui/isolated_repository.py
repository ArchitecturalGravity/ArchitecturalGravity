"""Disposable evidence destinations for provider-free production lifecycle tests."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory, gettempdir
from unittest.mock import patch

from AgMark.gui.application.history import discover_history
from AgMark.shared.runtime.artifacts import FilesystemArtifactStore, PublicationDestination


def external_evidence_directory(repository_root):
    """Allocate an explicitly external fixture even under the managed runtime.

    The GUI runtime pins default temporary storage inside the repository. That
    is appropriate for application scratch data, but not an external evidence
    publication destination. Use a disposable sibling in that case.
    """
    repository_root = Path(repository_root).resolve()
    temporary_root = Path(gettempdir()).resolve()
    if temporary_root == repository_root or repository_root in temporary_root.parents:
        temporary_root = repository_root.parent
    return TemporaryDirectory(prefix="agmark-evidence-test-", dir=temporary_root)


def isolate_repository(test, root_name, *, archive_backed=False):
    """Keep real registration/module authority, but publish only into temp storage.

    Copying the repository would break integrity-bound module-file identity.
    The shared artifact boundary explicitly supports external evidence roots.
    """
    # Flush each fixture's queued widget deletions after its cleanups. Without
    # an outer Qt event loop, processEvents does not deliver DeferredDelete;
    # old desktop trees otherwise survive and participate in later theme work.
    def finish_deferred_deletes():
        core = sys.modules.get("PySide6.QtCore")
        if core is not None and core.QCoreApplication.instance() is not None:
            core.QCoreApplication.sendPostedEvents(None, core.QEvent.Type.DeferredDelete)

    test.addCleanup(finish_deferred_deletes)
    repository_root = getattr(sys.modules[type(test).__module__], root_name)
    temporary = external_evidence_directory(repository_root)
    test.addCleanup(temporary.cleanup)
    test._test_evidence_root = Path(temporary.name)

    def isolated_store(destination):
        if archive_backed:
            # Archive/history tests exercise the actual central-store sealing
            # lifecycle in a disposable repository root, never the user's tree.
            return FilesystemArtifactStore(PublicationDestination.central(
                test._test_evidence_root / "AgMark" / "run_evidence",
                repository_root=test._test_evidence_root))
        target = test._test_evidence_root / destination.authority_root.name
        return FilesystemArtifactStore(PublicationDestination.external(
            target, repository_root=repository_root))

    # Repository-authority fixtures start with disposable evidence, including
    # read-only history discovery. User-retained generations are not fixture data.
    history_patcher = patch(
        "AgMark.gui.application.history.discover_history",
        side_effect=lambda _root: discover_history(test._test_evidence_root),
    )
    history_patcher.start()
    test.addCleanup(history_patcher.stop)

    patcher = patch("AgMark.gui.requests.resolver.FilesystemArtifactStore", side_effect=isolated_store)
    patcher.start()
    test.addCleanup(patcher.stop)
