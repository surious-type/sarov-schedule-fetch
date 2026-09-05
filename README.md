# Sarov schedule fetch

Hourly transport for MSU Sarov schedule PDFs.

The workflow is intended to run on a self-hosted GitHub Actions runner installed on the server that can reach `https://sarov.msu.ru`. It fetches the live schedule page, downloads the published 2nd-year PDFs, writes a manifest, and uploads everything as a short-lived GitHub Actions artifact named `sarov-schedule`.

PDFs are never committed to git. The artifact retention is 1 day.

## Runner

Install a self-hosted runner for this repository on the server and run it as a service. The workflow uses the labels:

`self-hosted, linux, x64`

## Manual test

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python fetch_schedule.py
find output -maxdepth 1 -type f -printf '%f\n'
cat output/manifest.json
```

## Schedule

The GitHub workflow runs every hour and can also be started manually with `workflow_dispatch`.

The matching ChatGPT calendar sync should run a few minutes after the fetch job and stay silent when the artifact is fresh and all calendar changes were imported successfully.
