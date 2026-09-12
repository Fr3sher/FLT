"""Owned finished gallery images and their explicitly persisted generation facts."""

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from .images import GalleryImages

__all__ = ['GalleryExportRecord', 'GalleryExports', 'prompt_with_trigger']


@dataclass(frozen=True)
class GalleryExportRecord:
    id: int
    dataset_id: int
    filename: str
    status: str
    record_id: int | None
    step: int | None
    checkpoint: str | None
    prompt: str | None
    inject_trigger: bool | None
    negative: str | None
    cfg: float | None
    steps: int | None
    sampler: str | None
    scheduler: str | None
    seed: int | None
    z_model: str | None
    strength: float | None
    extra_loras: str | None


class GalleryExports:
    def __init__(self, user_id):
        self._images = GalleryImages(user_id)

    def path(self, image_id):
        return self._path(self._images._row(image_id))

    @staticmethod
    def _path(row):
        """A current owned media file, confined to its dataset after symlink resolution."""
        if row is None or not row.filename:
            return None
        name = str(row.filename)
        if (Path(name).is_absolute() or PureWindowsPath(name).drive or ':' in name
                or '..' in name.replace('\\', '/').split('/')):
            return None
        from app.services.face_dataset_service import _dataset_dir
        try:
            root = Path(_dataset_dir(row.dataset_id)).resolve()
            path = (root / name).resolve(strict=True)
            if not path.is_relative_to(root) or not path.is_file():
                return None
            return str(path)
        except (OSError, ValueError, RuntimeError):
            return None

    def finished(self, image_ids):
        rows = (self._images._row(image_id) for image_id in image_ids)
        return tuple(GalleryExportRecord(**{key: getattr(row, key)
                                           for key in GalleryExportRecord.__dataclass_fields__})
                     for row in rows if row is not None and row.status == 'done' and self._path(row))


def prompt_with_trigger(prompt, trigger_word):
    from app.services.lora_test_studio import _prompt_with_trigger
    return _prompt_with_trigger(prompt, trigger_word)
