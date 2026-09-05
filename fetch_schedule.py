from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

BASE = "https://sarov.msu.ru"
SCHEDULE_URL = f"{BASE}/raspisanie"
OUT = Path("output")
TIMEOUT = 30
MAX_PDF_BYTES = 50 * 1024 * 1024
UA = "sarov-schedule-fetch/1.1 (+https://github.com/surious-type/sarov-schedule-fetch)"

SEMESTER_RE = re.compile(
    r"(Осенний|Весенний)\s+семестр\s+(\d{4})\s*[\\/]\s*(\d{4})\s+учебного\s+года",
    re.IGNORECASE,
)
COURSE_RE = re.compile(r"^(\d+)\s*курс$", re.IGNORECASE)
WEEK_RE = re.compile(r"неделя\s*(\d+)", re.IGNORECASE)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept": "*/*"})


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def no_query(url: str) -> str:
    p = urlparse(url)
    return p._replace(query="", fragment="").geturl()


def is_allowed_pdf_url(url: str) -> bool:
    p = urlparse(url)
    return (
        p.scheme == "https"
        and p.hostname == "sarov.msu.ru"
        and p.path.startswith("/sites/default/files/")
        and p.path.lower().endswith(".pdf")
    )


def week_number(label: str, url: str) -> int | None:
    m = WEEK_RE.search(label)
    if m:
        return int(m.group(1))

    decoded_name = unquote(Path(urlparse(url).path).name)
    m = re.search(r"(?:^|[_-])(\d{1,2})(?:[_-])", decoded_name)
    if m:
        return int(m.group(1))
    return None


def _semester_markers(soup: BeautifulSoup) -> list[tuple[tuple[int, int], str, NavigableString]]:
    markers: list[tuple[tuple[int, int], str, NavigableString]] = []
    for node in soup.find_all(string=True):
        text = normalize_text(str(node))
        m = SEMESTER_RE.search(text)
        if not m:
            continue
        title = normalize_text(m.group(0))
        markers.append(((int(m.group(2)), int(m.group(3))), title, node))
    return markers


def extract_course_pdf_links(page_text: str, course: int = 2) -> tuple[str, list[dict]]:
    """Return PDF links from the newest semester and the requested course block only."""
    soup = BeautifulSoup(page_text, "html.parser")
    markers = _semester_markers(soup)
    if not markers:
        raise RuntimeError("Could not find a semester heading on the live schedule page")

    _, semester_title, semester_node = max(markers, key=lambda item: item[0])

    in_course = False
    course_seen = False
    found: dict[str, dict] = {}

    for element in semester_node.next_elements:
        if isinstance(element, NavigableString):
            text = normalize_text(str(element))
            if not text:
                continue

            # A new semester means the selected semester block has ended.
            if SEMESTER_RE.search(text):
                break

            course_match = COURSE_RE.fullmatch(text)
            if course_match:
                seen_course = int(course_match.group(1))
                if seen_course == course:
                    in_course = True
                    course_seen = True
                    continue
                if in_course:
                    break
                continue

            if in_course and text.casefold() == "аспирантура":
                break

        if not in_course or not isinstance(element, Tag) or element.name != "a":
            continue

        href = (element.get("href") or "").strip()
        if not href:
            continue

        label = normalize_text(" ".join(element.stripped_strings))
        abs_url = no_query(urljoin(BASE, href))
        if not is_allowed_pdf_url(abs_url):
            continue

        found[abs_url] = {
            "label": label,
            "week_number": week_number(label, abs_url),
        }

    if not course_seen:
        raise RuntimeError(
            f"Could not find the '{course} курс' block inside semester '{semester_title}'"
        )
    if not found:
        raise RuntimeError(
            f"No published PDF links found for {course} course in semester '{semester_title}'"
        )

    links = [
        {"source_url": url, **meta}
        for url, meta in found.items()
    ]
    links.sort(
        key=lambda item: (
            item["week_number"] is None,
            item["week_number"] if item["week_number"] is not None else 10_000,
            item["source_url"],
        )
    )
    return semester_title, links


def fetch_bytes(url: str, *, expect_pdf: bool = False) -> tuple[bytes, str]:
    with SESSION.get(url, timeout=TIMEOUT, allow_redirects=True, stream=True) as r:
        r.raise_for_status()
        final = urlparse(r.url)
        if final.hostname != "sarov.msu.ru":
            raise RuntimeError(f"Unexpected redirect host: {final.hostname!r}")

        content_type = r.headers.get("content-type", "")
        length = r.headers.get("content-length")
        if length and int(length) > MAX_PDF_BYTES:
            raise RuntimeError(f"Upstream object too large: {length} bytes")

        chunks: list[bytes] = []
        total = 0
        for chunk in r.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if expect_pdf and total > MAX_PDF_BYTES:
                raise RuntimeError(f"PDF exceeds {MAX_PDF_BYTES} bytes")
            chunks.append(chunk)

        data = b"".join(chunks)

        if expect_pdf and not data.startswith(b"%PDF"):
            raise RuntimeError(f"Not a PDF: {url} (content-type={content_type!r})")
        return data, content_type


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    page_bytes, page_ct = fetch_bytes(SCHEDULE_URL)
    page_text = page_bytes.decode("utf-8", errors="replace")
    (OUT / "raspisanie.html").write_text(page_text, encoding="utf-8")

    semester_title, links = extract_course_pdf_links(page_text, course=2)

    files = []
    for idx, meta in enumerate(links, start=1):
        url = meta["source_url"]
        data, content_type = fetch_bytes(url, expect_pdf=True)
        source_name = unquote(Path(urlparse(url).path).name)
        safe_name = re.sub(r"[^0-9A-Za-zА-Яа-яЁё._-]+", "_", source_name).strip("_")
        if not safe_name.lower().endswith(".pdf"):
            safe_name += ".pdf"
        file_name = f"{idx:02d}_{safe_name}"
        (OUT / file_name).write_bytes(data)
        files.append(
            {
                "file": file_name,
                "label": meta["label"],
                "week_number": meta["week_number"],
                "source_url": url,
                "content_type": content_type,
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )

    manifest = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": SCHEDULE_URL,
        "semester": semester_title,
        "course": 2,
        "page_content_type": page_ct,
        "pdf_count": len(files),
        "files": files,
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
