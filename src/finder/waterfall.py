"""
Finder waterfall for the Cold Email Pipeline.

Given a company + domain, finds the CTO / technical lead's name and
email via a 5-level waterfall.  Stops at the first confident result.

Levels:
  L1  Team-page scraping  → spaCy NER → role_match → email on page
  L2  GitHub API          → member bios → role_match → profile email
  L3  DuckDuckGo search   → extract name from snippet
  L4  Email permutations
  L5  Gravatar MD5 check  → verified or default pattern

No SMTP verification (decisions.md D005).
No LinkedIn scraping (agent_project.md Section 4).

Conforms to:
 - contracts.md 3.2, 3.4, 3.6  (enums, schemas)
 - build_plan.md Module 4
"""

import hashlib
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup

from src.finder.role_match import find_technical_lead

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# spaCy lazy loader (avoid import-time download)
# ---------------------------------------------------------------------------

_NLP = None


def _get_nlp():
    """Lazy-load spaCy en_core_web_sm."""
    global _NLP
    if _NLP is None:
        import spacy

        _NLP = spacy.load("en_core_web_sm")
    return _NLP


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


def _extract_names(text: str) -> list[str]:
    """Run spaCy NER and return a list of PERSON entity strings."""
    nlp = _get_nlp()
    doc = nlp(text[:50_000])  # limit to avoid memory issues
    return list({ent.text.strip() for ent in doc.ents if ent.label_ == "PERSON"})


def _find_emails_on_page(text: str) -> list[str]:
    """Return all email-like strings found in *text*."""
    return _EMAIL_RE.findall(text)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def generate_permutations(first: str, last: str, domain: str) -> list[str]:
    """Generate 8 common email patterns for *first*.*last*@*domain*.

    All returned addresses are lowercased.
    """
    f = first.lower().strip()
    l = last.lower().strip()
    d = domain.lower().strip()
    return [
        f"{f}@{d}",
        f"{f}.{l}@{d}",
        f"{f[0]}{l}@{d}",
        f"{f[0]}.{l}@{d}",
        f"{f}{l}@{d}",
        f"{l}@{d}",
        f"{f}_{l}@{d}",
        f"{l}{f[0]}@{d}",
    ]


def check_gravatar(email: str) -> bool:
    """Return *True* if *email* has a Gravatar profile.

    Uses the ``?d=404`` trick: Gravatar returns 404 when no image
    exists for the hash instead of a default placeholder.
    """
    h = hashlib.md5(email.lower().strip().encode()).hexdigest()
    url = f"https://gravatar.com/avatar/{h}?d=404"
    try:
        resp = requests.get(url, timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        logger.warning("Gravatar request failed for %s", email)
        return False


# ---------------------------------------------------------------------------
# L1 — Team-page scraping
# ---------------------------------------------------------------------------

_TEAM_PATHS = ["/about", "/team", "/leadership", "/people"]


def _scrape_team_pages(
    domain: str,
) -> Optional[dict]:
    """L1: scrape common team pages, NER → role_match → email.

    Returns ``{name, title, email, source, confidence}`` or ``None``.
    """
    for path in _TEAM_PATHS:
        url = f"https://{domain}{path}"
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
        except requests.RequestException:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        page_text = soup.get_text(separator=" ", strip=True)

        names = _extract_names(page_text)
        if not names:
            continue

        match = find_technical_lead(page_text, names)
        if match is None:
            continue

        name, title = match

        # Look for an email on the page
        emails = _find_emails_on_page(page_text)
        # Prefer email containing the person's first name
        first_lower = name.split()[0].lower() if name.split() else ""
        picked = None
        for e in emails:
            if first_lower and first_lower in e.lower():
                picked = e
                break
        if picked is None and emails:
            picked = emails[0]

        if picked:
            logger.info("L1 direct email found: %s → %s", name, picked)
            return {
                "name": name,
                "title": title,
                "email": picked,
                "source": "team_page",
                "confidence": "direct_find",
            }
        else:
            # Name + title found but no email on page → continue to L2
            # but remember the name for later permutation
            logger.info("L1 name found (no email): %s / %s", name, title)
            return {
                "name": name,
                "title": title,
                "email": None,
                "source": "team_page",
                "confidence": None,
            }

    return None


# ---------------------------------------------------------------------------
# L2 — GitHub API
# ---------------------------------------------------------------------------


def _search_github(
    company: str, domain: str
) -> Optional[dict]:
    """L2: search GitHub orgs/users by domain → NER on bios → role_match.

    Uses ``GITHUB_TOKEN`` env var for authenticated requests.
    Returns ``{name, title, email, source, confidence}`` or ``None``.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logger.warning("GITHUB_TOKEN not set — skipping L2")
        return None

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
    }

    # Search for org by domain-derived name
    org_guess = domain.split(".")[0]  # e.g. "acme" from "acme.com"
    try:
        resp = requests.get(
            f"https://api.github.com/orgs/{org_guess}/members",
            headers=headers,
            timeout=10,
        )
        if resp.status_code != 200:
            logger.debug("GitHub org lookup failed for %s: %d", org_guess, resp.status_code)
            return None
    except requests.RequestException:
        return None

    members = resp.json()
    if not isinstance(members, list):
        return None

    all_names: list[str] = []
    all_bios: str = ""
    email_map: dict[str, str] = {}  # name → email

    for member in members[:20]:  # cap at 20 members
        login = member.get("login", "")
        try:
            user_resp = requests.get(
                f"https://api.github.com/users/{login}",
                headers=headers,
                timeout=10,
            )
            if user_resp.status_code != 200:
                continue
        except requests.RequestException:
            continue

        user = user_resp.json()
        name = user.get("name") or ""
        bio = user.get("bio") or ""
        email = user.get("email") or ""

        if name:
            all_names.append(name)
            all_bios += f" {name} {bio}"
            if email:
                email_map[name] = email

        time.sleep(0.5)  # be polite

    if not all_names:
        return None

    match = find_technical_lead(all_bios, all_names)
    if match is None:
        return None

    name, title = match
    gh_email = email_map.get(name)

    if gh_email:
        logger.info("L2 GitHub email found: %s → %s", name, gh_email)
        return {
            "name": name,
            "title": title,
            "email": gh_email,
            "source": "github",
            "confidence": "direct_find",
        }
    else:
        logger.info("L2 GitHub name found (no email): %s / %s", name, title)
        return {
            "name": name,
            "title": title,
            "email": None,
            "source": "github",
            "confidence": None,
        }


# ---------------------------------------------------------------------------
# L3 — DuckDuckGo search
# ---------------------------------------------------------------------------


def _search_duckduckgo(
    company: str, domain: str
) -> Optional[dict]:
    """L3: DuckDuckGo search for CTO name.  Max 5 queries, 5-10s delays.

    Returns ``{name, title}`` (no email) or ``None``.
    """
    queries = [
        f"{company} CTO",
        f'"{company}" CTO email',
        f"site:{domain} CTO",
        f"{company} Chief Technology Officer",
        f"{company} VP Engineering",
    ]

    for i, q in enumerate(queries):
        if i > 0:
            time.sleep(random.uniform(5, 10))

        try:
            resp = requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": q},
                headers=_HEADERS,
                timeout=10,
            )
            if resp.status_code != 200:
                continue
        except requests.RequestException:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        snippets = soup.select(".result__snippet")
        all_text = " ".join(s.get_text(" ", strip=True) for s in snippets[:5])

        if not all_text:
            continue

        names = _extract_names(all_text)
        if not names:
            continue

        match = find_technical_lead(all_text, names)
        if match:
            name, title = match
            logger.info("L3 DDG name found: %s / %s (query=%r)", name, title, q)
            return {"name": name, "title": title}

    return None


# ---------------------------------------------------------------------------
# Main waterfall
# ---------------------------------------------------------------------------


def find_contact(
    company: str, domain: str, db_conn=None
) -> Optional[dict]:
    """Run the 5-level finder waterfall.

    Returns ``{name, title, email, source, confidence}`` or ``None``.
    """
    logger.info("Finder waterfall: company=%r  domain=%r", company, domain)

    # ------ L1: Team pages ------
    l1 = _scrape_team_pages(domain)
    if l1 and l1.get("email"):
        return l1  # direct find — done

    # Carry forward name/title from L1 if found
    found_name = l1["name"] if l1 else None
    found_title = l1["title"] if l1 else None
    found_source = l1["source"] if l1 else None

    # ------ L2: GitHub ------
    if not found_name:
        l2 = _search_github(company, domain)
        if l2 and l2.get("email"):
            return l2  # direct find — done
        if l2:
            found_name = l2["name"]
            found_title = l2["title"]
            found_source = l2["source"]

    # ------ L3: DuckDuckGo ------
    if not found_name:
        l3 = _search_duckduckgo(company, domain)
        if l3:
            found_name = l3["name"]
            found_title = l3["title"]
            found_source = "duckduckgo"

    # If we still have no name, give up
    if not found_name:
        logger.warning("Finder waterfall: no name found for %s", domain)
        return None

    # ------ L4 + L5: Permutations + Gravatar ------
    parts = found_name.strip().split()
    if len(parts) < 2:
        first, last = parts[0], ""
    else:
        first, last = parts[0], parts[-1]

    if last:
        perms = generate_permutations(first, last, domain)
    else:
        # Only first name available — single pattern
        perms = [f"{first.lower()}@{domain.lower()}"]

    # L5: Gravatar verification
    for email in perms:
        if check_gravatar(email):
            logger.info("L5 Gravatar verified: %s", email)
            return {
                "name": found_name,
                "title": found_title or "",
                "email": email,
                "source": "permutation",
                "confidence": "gravatar_verified",
            }

    # No Gravatar hit — use first@domain as default
    default_email = f"{first.lower()}@{domain.lower()}"
    logger.info("L5 default pattern: %s", default_email)
    return {
        "name": found_name,
        "title": found_title or "",
        "email": default_email,
        "source": "permutation",
        "confidence": "default_pattern",
    }
