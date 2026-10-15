"""Adapter for the JSON endpoints used by public Workday career sites.

These browser endpoints are not a documented, supported integration API.
Only public external boards are read; no login or application submission.
"""
from __future__ import annotations

import re
import time
from urllib.parse import unquote, urlsplit

import requests

from .fetch import Job, TIMEOUT, UA, strip_html

PAGE_SIZE = 20
MAX_PAGES = 100
REQUEST_DELAY = 0.1


def board_parts(url: str) -> tuple[str, str, str]:
    """Return origin, tenant, and site from a verified external board URL."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    match = re.fullmatch(r"([a-z0-9-]+)(?:\.wd\d+)?\.myworkdayjobs\.com", host)
    path = [unquote(p) for p in parts.path.strip("/").split("/") if p]
    if path and re.fullmatch(r"[a-z]{2,3}-[A-Z]{2}", path[0]):
        path.pop(0)
    if (parts.scheme != "https" or not match or parts.username or parts.password
            or parts.netloc != host or parts.query or parts.fragment
            or len(path) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]+", path[0])):
        raise ValueError("Workday slug must be an HTTPS myworkdayjobs.com career-board URL")
    return f"https://{host}", match.group(1), path[0]


def parse_workday(board_url: str, company: str, body: dict) -> list[Job]:
    """Parse a full job-detail response, using its actual publication date."""
    origin, tenant, site = board_parts(board_url)
    info = body.get("jobPostingInfo") or {}
    identity = info.get("jobReqId") or info.get("id")
    if (not identity or not info.get("title") or not info.get("jobDescription")
            or not info.get("externalUrl")):
        return []
    locations = [info.get("location") or ""]
    for location in info.get("additionalLocations") or []:
        if isinstance(location, dict):
            location = location.get("descriptor") or location.get("location") or ""
        if isinstance(location, str):
            locations.append(location)
    country = (info.get("country") or {}).get("descriptor")
    if country:
        locations.append(country)
    return [Job(
        job_id=f"workday:{tenant}:{site}:{identity}",
        ats="workday", company=company, title=info["title"].strip(),
        location="; ".join(dict.fromkeys(loc for loc in locations if loc)),
        url=info["externalUrl"],
        description=strip_html(info["jobDescription"]),
        posted_at=info.get("startDate"),
    )]


def fetch_workday(board_url: str, company: str | None = None,
                  session: requests.Session | None = None) -> list[Job]:
    origin, tenant, site = board_parts(board_url)
    company = company or tenant
    api = f"{origin}/wday/cxs/{tenant}/{site}"
    sess = session or requests.Session()
    headers = {**UA, "Accept": "application/json"}
    jobs: list[Job] = []
    paths: set[str] = set()
    identities: set[str] = set()
    offset = 0
    for _ in range(MAX_PAGES):
        try:
            response = sess.post(
                f"{api}/jobs", headers=headers, timeout=TIMEOUT,
                json={"appliedFacets": {}, "limit": PAGE_SIZE,
                      "offset": offset, "searchText": ""},
            )
            response.raise_for_status()
            body = response.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"  ! workday/{tenant}/{site}: list offset {offset} failed ({type(exc).__name__})")
            break
        postings = body.get("jobPostings") or []
        if not postings:
            break
        new_paths = 0
        for posting in postings:
            path = posting.get("externalPath") or ""
            if not path.startswith("/job/") or path in paths or "/../" in path:
                continue
            paths.add(path)
            new_paths += 1
            time.sleep(REQUEST_DELAY)
            try:
                detail = sess.get(f"{api}{path}", headers=headers, timeout=TIMEOUT)
                detail.raise_for_status()
                parsed = parse_workday(board_url, company, detail.json())
                if not parsed:
                    print(f"  ! workday/{tenant}/{site}: incomplete detail skipped")
                for job in parsed:
                    if job.job_id not in identities:
                        identities.add(job.job_id)
                        jobs.append(job)
            except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
                print(f"  ! workday/{tenant}/{site}: job detail skipped ({type(exc).__name__})")
        offset += len(postings)
        total = body.get("total")
        if not new_paths:
            print(f"  ! workday/{tenant}/{site}: repeated listing page; stopped pagination")
            break
        if isinstance(total, int) and offset >= total:
            break
        # Some tenants return fewer than 20 items even before the last page.
        time.sleep(REQUEST_DELAY)
    else:
        print(f"  ! workday/{tenant}/{site}: stopped at {MAX_PAGES} pages; board may be incomplete")
    return jobs
