import re

from hr_assist.corpus import ManifestEntry, ManifestError
from hr_assist.ingestion.parser import Page

_RUNNING_HEADER = re.compile(r"^.+\|\s*(NDS-[A-Z0-9-]+)\s*\|\s*(v[\d.]+)$")
_BOILERPLATE = [
    _RUNNING_HEADER,
    re.compile(r"^\*\*Northstar Digital Services Ltd\.\*\*$"),
    re.compile(r"^\*\*SUPERSEDED — NOT FOR CURRENT POLICY DECISIONS\*\*$"),  # archived banner
    re.compile(r"^Internal(?:\s+\(ARCHIVED\))?\s+·\s+.+$"),  # running footer
    re.compile(r"^Page \d+ of \d+$"),
]


def check_running_header(entry: ManifestEntry, pages: list[Page]) -> None:
    """Fails unless every running header names the manifest's Document ID and Version (ADR 0001)."""
    expected = (entry.document_id, entry.document_version)
    found = {
        heading.groups()
        for page in pages
        for line in page.text.splitlines()
        if (heading := _RUNNING_HEADER.match(line.strip()))
    }
    if found != {expected}:
        printed = ", ".join(" ".join(h) for h in sorted(found)) or "no running header"
        raise ManifestError(
            f"Manifest describes {entry.path.name} as {' '.join(expected)}, "
            f"but its running header says {printed}"
        )


def normalise(pages: list[Page]) -> list[Page]:
    """Strips the running header, footer and superseded banner from every page."""
    return [Page(page.number, _strip_boilerplate(page.text)) for page in pages]


def _strip_boilerplate(text: str) -> str:
    lines = [line for line in text.splitlines() if not _is_boilerplate(line.strip())]
    return "\n".join(lines)


def _is_boilerplate(line: str) -> bool:
    return any(pattern.match(line) for pattern in _BOILERPLATE)
