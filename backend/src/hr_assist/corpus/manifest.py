from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from hr_assist.settings import REPO_ROOT

DocumentKind = Literal["policy_document", "summary_deck", "test_fixture"]
DocumentStatus = Literal["current", "superseded"]

DEFAULT_MANIFEST = REPO_ROOT / "data" / "manifest.yaml"


class ManifestError(Exception):
    """The Corpus Manifest is missing, malformed or describes a document inconsistently."""


class ManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: Path
    document_id: str = Field(min_length=1)
    document_version: str = Field(min_length=1)
    title: str = Field(min_length=1)
    kind: DocumentKind
    status: DocumentStatus
    effective_from: date
    effective_to: date | None
    superseded_by: str | None = None

    @model_validator(mode="after")
    def _effective_period_is_ordered(self) -> "ManifestEntry":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to is before effective_from")
        return self


def load_manifest(path: Path = DEFAULT_MANIFEST, root: Path = REPO_ROOT) -> list[ManifestEntry]:
    """Read the Corpus Manifest, resolving each document path against the repo root."""
    try:
        raw = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise ManifestError(f"Cannot read manifest {path}: {exc}") from exc
    if not isinstance(raw, list):
        raise ManifestError(f"Manifest {path} must be a list of documents")

    entries = []
    for position, item in enumerate(raw, start=1):
        try:
            entry = ManifestEntry.model_validate(item)
        except ValidationError as exc:
            raise ManifestError(f"Manifest entry {position} is invalid: {exc}") from exc
        entries.append(entry.model_copy(update={"path": root / entry.path}))
    return entries
