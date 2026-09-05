# Sarov schedule fetch

Hourly transport for MSU Sarov schedule PDFs.

The workflow runs on a GitHub-hosted `ubuntu-latest` runner. It fetches the live page at `https://sarov.msu.ru/raspisanie`, selects the newest semester shown on that page, enters only the `2 курс` block, downloads the published PDF links from that block, writes a manifest, and uploads everything as a short-lived GitHub Actions artifact named `sarov-schedule`.

PDFs are never committed to git. The artifact retention is 1 day.

## Selection rules

The parser deliberately does **not** scan the whole page for filenames containing `2`.

It:

1. finds all semester headings matching `Осенний/Весенний семестр YYYY/YYYY учебного года`;
2. selects the newest academic year;
3. starts collecting links only after the exact `2 курс` marker;
4. stops when the next course / postgraduate section begins;
5. accepts only HTTPS PDF URLs on `sarov.msu.ru/sites/default/files/`.

The manifest includes `semester`, `course`, `week_number`, the original `source_url`, file size, and SHA-256 for each PDF.

## Manual test

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
python fetch_schedule.py
find output -maxdepth 1 -type f -printf '%f\n'
cat output/manifest.json
```

## Schedule

The main workflow runs every hour at minute 2 and can also be started manually with `workflow_dispatch`.

A push that changes the fetcher, tests, requirements, or workflow also runs the same validation/fetch job so parser changes are checked immediately.

The matching ChatGPT calendar sync runs after the fetch and stays silent when the artifact is fresh and all calendar changes were imported successfully.
