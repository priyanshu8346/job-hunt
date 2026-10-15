"""Public SmartRecruiters, Workable, and Recruitee career-board adapters."""
from __future__ import annotations

import os
import re
import time
from typing import Any

import requests

from .fetch import Job, TIMEOUT, UA, strip_html

PAGE_SIZE = 100
MAX_PAGES = 100
REQUEST_DELAY = 0.1


def validate_slug(slug: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", slug):
        raise ValueError("Use the verified company identifier, not a URL, for this ATS")
    return slug


def _date(value: str | None) -> str | None:
    # Recruitee uses '2026-10-15 08:22:05 UTC', unlike the other feeds' ISO dates.
    return value.replace(" UTC", "+00:00") if value else None


def _location(location: dict) -> str:
    if location.get("fullLocation"):
        return location["fullLocation"]
    parts = [location.get("city"), location.get("region") or location.get("state"),
             location.get("country") or location.get("country_name")]
    parts = ["India" if str(p).lower() == "in" else str(p) for p in parts if p]
    return ", ".join(dict.fromkeys(parts))


def _merge(jobs: list[Job]) -> list[Job]:
    """Workable may repeat a shortcode once per location; keep all locations."""
    unique: dict[str, Job] = {}
    for job in jobs:
        existing = unique.get(job.job_id)
        if existing:
            existing.location = "; ".join(dict.fromkeys(
                part for j in (existing, job) for part in j.location.split("; ") if part))
        else:
            unique[job.job_id] = job
    return list(unique.values())


def parse_smartrecruiters(slug: str, company: str, body: dict) -> list[Job]:
    """Parse a full posting, including qualifications and additional sections."""
    identity = body.get("id") or body.get("uuid")
    sections = (body.get("jobAd") or {}).get("sections") or {}
    order = ["jobDescription", "qualifications", "additionalInformation", "companyDescription"]
    order.extend(key for key in sections if key not in order)
    description = "\n\n".join(strip_html((sections.get(key) or {}).get("text"))
                                  for key in order if (sections.get(key) or {}).get("text"))
    url = body.get("postingUrl") or body.get("applyUrl")
    if (not identity or not body.get("name") or not description or not url
            or body.get("active") is False
            or body.get("visibility", "PUBLIC") != "PUBLIC"):
        return []
    location = body.get("location") or {}
    loc = _location(location)
    if location.get("remote"):
        loc = f"{loc}; Remote" if loc else "Remote"
    return [Job(job_id=f"smartrecruiters:{slug}:{identity}", ats="smartrecruiters",
                company=company, title=body["name"].strip(), location=loc,
                url=url, description=description, posted_at=_date(body.get("releasedDate")))]


def parse_workable(slug: str, company: str, body: dict) -> list[Job]:
    out = []
    for row in body.get("jobs") or []:
        identity = row.get("shortcode")
        description = "\n\n".join(strip_html(row.get(key)) for key in
                                      ("description", "requirements", "benefits") if row.get(key))
        url = row.get("url") or row.get("shortlink") or row.get("application_url")
        # This endpoint returns published jobs only. 'state' is a geographic
        # region (e.g. Karnataka), not a publication status.
        if not identity or not row.get("title") or not description or not url:
            continue
        locations = [_location(loc) for loc in row.get("locations") or []
                     if isinstance(loc, dict) and not loc.get("hidden")]
        if not locations:
            locations = [_location(row)]
        if row.get("telecommuting"):
            locations.append("Remote")
        out.append(Job(job_id=f"workable:{slug}:{identity}", ats="workable", company=company,
                       title=row["title"].strip(),
                       location="; ".join(dict.fromkeys(loc for loc in locations if loc)),
                       url=url, description=description,
                       posted_at=_date(row.get("published_on") or row.get("created_at"))))
    return _merge(out)


def parse_recruitee(slug: str, company: str, body: dict) -> list[Job]:
    out = []
    for row in body.get("offers") or []:
        identity = row.get("id") or row.get("guid")
        description = "\n\n".join(strip_html(row.get(key)) for key in
                                      ("description", "requirements") if row.get(key))
        url = row.get("careers_url") or row.get("careers_apply_url")
        if (not identity or not row.get("title") or not description or not url
                or (row.get("status") or "published") != "published"):
            continue
        locations = [row.get("location") or _location(row)]
        locations.extend(_location(loc) for loc in row.get("locations") or [] if isinstance(loc, dict))
        if row.get("remote"):
            locations.append("Remote")
        out.append(Job(job_id=f"recruitee:{slug}:{identity}", ats="recruitee", company=company,
                       title=row["title"].strip(),
                       location="; ".join(dict.fromkeys(loc for loc in locations if loc)),
                       url=url, description=description,
                       posted_at=_date(row.get("published_at") or row.get("created_at"))))
    return _merge(out)


def _get(session: Any, url: str, **kwargs) -> dict:
    response = session.get(url, headers=kwargs.pop("headers", UA), timeout=TIMEOUT, **kwargs)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise ValueError("Expected a JSON object from the career board")
    return body


def fetch_smartrecruiters(slug: str, company: str | None = None,
                          session: requests.Session | None = None) -> list[Job]:
    validate_slug(slug)
    sess = session or requests.Session()
    base = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    jobs, seen = [], set()
    offset = 0
    for _ in range(MAX_PAGES):
        try:
            body = _get(sess, base, params={"limit": PAGE_SIZE, "offset": offset})
        except (requests.RequestException, ValueError) as exc:
            print(f"  ! smartrecruiters/{slug}: list offset {offset} failed ({type(exc).__name__})")
            break
        postings = body.get("content") or []
        if not postings:
            break
        new = 0
        for posting in postings:
            identity = posting.get("id") or posting.get("uuid")
            if not identity or str(identity) in seen:
                continue
            identity = str(identity)
            if not re.fullmatch(r"[A-Za-z0-9_-]+", identity):
                continue
            seen.add(identity); new += 1
            time.sleep(REQUEST_DELAY)
            try:
                # Construct the detail URL; never follow an arbitrary 'ref' URL from a feed.
                detail = _get(sess, f"{base}/{identity}")
                parsed = parse_smartrecruiters(slug, company or slug, detail)
                jobs.extend(parsed)
                if not parsed and detail.get("active") is not False:
                    print(f"  ! smartrecruiters/{slug}: incomplete/nonpublic detail {identity} skipped")
            except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
                print(f"  ! smartrecruiters/{slug}: detail {identity} skipped ({type(exc).__name__})")
        offset += len(postings)
        if not new:
            print(f"  ! smartrecruiters/{slug}: repeated page; stopped pagination")
            break
        if isinstance(body.get("totalFound"), int) and offset >= body["totalFound"]:
            break
        time.sleep(REQUEST_DELAY)
    else:
        print(f"  ! smartrecruiters/{slug}: stopped at {MAX_PAGES} pages; board may be incomplete")
    return _merge(jobs)


def fetch_workable(slug: str, company: str | None = None,
                   session: requests.Session | None = None) -> list[Job]:
    validate_slug(slug)
    # Documented public endpoint returns all published jobs, with descriptions.
    body = _get(session or requests.Session(), f"https://www.workable.com/api/accounts/{slug}",
                params={"details": "true"})
    return parse_workable(slug, company or slug, body)


def fetch_recruitee(slug: str, company: str | None = None,
                    session: requests.Session | None = None) -> list[Job]:
    validate_slug(slug)
    # Employer-scoped, optional token; never send one company's token to another.
    env = "RECRUITEE_CAREERS_TOKEN_" + re.sub(r"[^A-Z0-9]", "_", slug.upper())
    token = os.getenv(env)
    headers = dict(UA)
    if token:
        headers["X-Careers-Sites-Token"] = token
    try:
        body = _get(session or requests.Session(), f"https://{slug}.recruitee.com/api/offers/",
                    headers=headers)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 401:
            print(f"  ! recruitee/{slug}: board requires an employer-provided token in {env}")
            return []
        raise
    return parse_recruitee(slug, company or slug, body)
