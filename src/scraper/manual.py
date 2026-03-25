"""
Manual queue loader for the Cold Email Pipeline.

Reads ``data/manual_queue.json`` — a JSON array of manually curated job entries.

**Required keys per entry:** ``company``, ``domain``, ``jd_summary``
**Optional keys:** ``url``, ``title``

``job_id`` = SHA-256 of ``url`` if present, else SHA-256 of ``company + domain``.
``title`` defaults to ``company`` if not provided.
``source`` is always ``"manual"``.

Conforms to contracts.md Section 3.6 and Section 6.2.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = {"company", "domain", "jd_summary"}


def load_manual_queue(filepath: str) -> list[dict]:
    """Load and validate entries from a manual queue JSON file.

    Error handling (per contracts.md FC-03 / Section 6.2):
    * Missing file → ``[]`` + ``logger.warning``.
    * Empty file   → ``[]``.
    * Invalid JSON → ``[]`` + ``logger.warning``.
    * Entries missing required keys are skipped with a warning.
    """
    path = Path(filepath)

    if not path.exists():
        logger.warning("Manual queue file not found: %s", filepath)
        return []

    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in manual queue file: %s", filepath)
        return []

    if not isinstance(data, list):
        logger.warning("Manual queue root is not a list: %s", filepath)
        return []

    jobs: list[dict] = []
    for idx, entry in enumerate(data):
        if not isinstance(entry, dict):
            logger.warning("Entry %d is not a dict, skipped", idx)
            continue

        missing = _REQUIRED_KEYS - entry.keys()
        if missing:
            logger.warning("Entry %d missing keys %s, skipped", idx, missing)
            continue

        company = entry["company"]
        domain = entry["domain"]
        url = entry.get("url", "")
        title = entry.get("title", company)  # fallback to company name

        if url:
            job_id = hashlib.sha256(url.encode()).hexdigest()
        else:
            job_id = hashlib.sha256(f"{company}{domain}".encode()).hexdigest()

        jobs.append({
            "job_id": job_id,
            "title": title,
            "company": company,
            "domain": domain,
            "url": url,
            "source": "manual",
            "jd_summary": entry["jd_summary"],
            "discovered_at": datetime.now(timezone.utc).isoformat(),
        })

    logger.info("Manual queue: %d valid entries from %s", len(jobs), filepath)
    return jobs
