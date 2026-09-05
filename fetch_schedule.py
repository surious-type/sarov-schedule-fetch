from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://sarov.msu.ru"
SCHEDULE_URL = f"{BASE}/raspisanie"
OUT = Path("output")
TIMEOUT = 30
MAX_PDF_BYTES = 50 * 1024 * 1024
UA = "sarov-schedule-fetch/1.0 (+https://github.com/surious-type/sarov-schedule-fetch)"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept": "*/*"})


def no_query(url: str) -> str:
    p = urlparse(url)
    return p._replace(query="", fragment="").geturl()


def is_second_course_pdf(href: str, label: str) -> bool:
    decoded = unquote(href).lower()
    label_l = label.lower()
    if not decoded.endswith(".pdf"):
        return False
    if "/sites/default/files/" not in decoded:
        return False

    name = Path(urlparse(decoded).path).name
    patterns = (
        r"(^|[_\-\s])2([_\-\s]|$)",
        r"2[_\-\s]*курс",
        r"2[_\-\s]*kurs",
        r"курс[_\-\s]*2",
        r"course[_\-\s]*2",
    )
    return any(re.search(p, name) for p in patterns) or "2 курс" in label_l


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

        if expect_pdf:
            if not data.startswith(b"%PDF"):
                raise RuntimeError(f"Not a PDF: {url} (content-type={content_type!r})")
        return data, content_type


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    page_bytes, page_ct = fetch_bytes(SCHEDULE_URL)
    page_text = page_bytes.decode("utf-8", errors="replace")
    (OUT / "raspisanie.html").write_text(page_text, encoding="utf-8")

    soup = BeautifulSoup(page_text, "html.parser")
    found: dict[str, dict] = {}

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        label = " ".join(a.stripped_strings).strip()
        abs_url = no_query(urljoin(BASE, href))
        if is_second_course_pdf(abs_url, label):
            found[abs_url] = {"label": label}

    if not found:
        raise RuntimeError("No 2nd-year PDF links found on the live schedule page")

    files = []
    for idx, (url, meta) in enumerate(sorted(found.items()), start=1):
        data, content_type = fetch_bytes(url, expect_pdf=True)
        source_name = unquote(Path(urlparse(url).path).name)
        safe_name = re.sub(r"[^0-9A-Za-zА-Яа-яЁё._-]+", "_", source_name).strip("_")
        if not safe_name.lower().endswith(".pdf"):
            safe_name += ".pdf"
        file_name = f"{idx:02d}_{safe_name}"
        path = OUT / file_name
        path.write_bytes(data)
        files.append(
            {
                "file": file_name,
                "label": meta["label"],
                "source_url": url,
                "content_type": content_type,
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )

    manifest = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": SCHEDULE_URL,
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
