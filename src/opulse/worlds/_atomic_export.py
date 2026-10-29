"""Publish an exported directory and its companion JSON file after writing both."""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def staged_export(folder: Path, sidecar: Path) -> Iterator[tuple[Path, Path]]:
    """Yield sibling staging paths, then publish them together with rollback on failure."""
    folder.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=f".{folder.name}.tmp-", dir=folder.parent))
    staged_sidecar = staged.parent / f"{staged.name}.json"
    backup = None
    installed = False
    published = False
    try:
        yield staged, staged_sidecar
        if folder.exists():
            backup = Path(tempfile.mkdtemp(prefix=f".{folder.name}.old-", dir=folder.parent))
            backup.rmdir()
            folder.rename(backup)
        try:
            staged.rename(folder)
            installed = True
            staged_sidecar.replace(sidecar)
            published = True
        except BaseException:
            if installed:
                folder.rename(staged)
            if backup is not None:
                backup.rename(folder)
                backup = None
            raise
    finally:
        if staged.exists():
            shutil.rmtree(staged)
        staged_sidecar.unlink(missing_ok=True)
        if published and backup is not None and backup.exists():
            shutil.rmtree(backup)
