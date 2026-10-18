import re

from hr_assist.ingestion.parser import Page

_BOILERPLATE = [
    re.compile(r"^.+\|\s*NDS-[A-Z0-9-]+\s*\|\s*v[\d.]+$"),  # running header
    re.compile(r"^\*\*Northstar Digital Services Ltd\.\*\*$"),
    re.compile(r"^Internal\s+·\s+.+$"),  # running footer
    re.compile(r"^Page \d+ of \d+$"),
]


def normalise(pages: list[Page]) -> list[Page]:
    """Strips the running header and footer from every page."""
    return [Page(page.number, _strip_boilerplate(page.text)) for page in pages]


def _strip_boilerplate(text: str) -> str:
    lines = [line for line in text.splitlines() if not _is_boilerplate(line.strip())]
    return "\n".join(lines)


def _is_boilerplate(line: str) -> bool:
    return any(pattern.match(line) for pattern in _BOILERPLATE)
