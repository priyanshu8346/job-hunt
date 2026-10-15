"""Read additional public career feeds and advertised JobPosting metadata."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import json
import re
import time
from urllib.parse import urljoin, urlsplit
import xml.etree.ElementTree as ET

import requests

from .boards import validate_slug, _merge
from .fetch import Job, TIMEOUT, UA, strip_html

PAGE_SIZE = 100
MAX_PAGES = 100
MAX_DETAILS = 2000
REQUEST_DELAY = 0.1
TT = {"tt": "https://teamtailor.com/locations"}


def origin(slug: str, domain: str) -> str:
    if "://" not in slug:
        validate_slug(slug)
        return f"https://{slug}.{domain}"
    p = urlsplit(slug)
    host = p.hostname or ""
    if (p.scheme != "https" or p.netloc != host or not host.endswith("." + domain)
            or p.path not in ("", "/") or p.query or p.fragment):
        raise ValueError(f"Use a verified HTTPS company root under {domain}")
    return f"https://{host}"


def _xml(raw: bytes | str) -> ET.Element:
    check = raw.upper() if isinstance(raw, bytes) else raw.upper().encode()
    if b"<!DOCTYPE" in check or b"<!ENTITY" in check:
        raise ValueError("DTD/entity declarations are not supported in job feeds")
    return ET.fromstring(raw)


def _text(node: ET.Element, path: str) -> str:
    child = node.find(path)
    return "".join(child.itertext()).strip() if child is not None else ""


def _response(session, url: str, **kwargs):
    response = session.get(url, headers=UA, timeout=TIMEOUT, **kwargs)
    response.raise_for_status()
    return response


def parse_personio(slug: str, company: str, raw: bytes | str) -> list[Job]:
    base = origin(slug, "jobs.personio.de") if "jobs.personio.com" not in slug else origin(slug, "jobs.personio.com")
    jobs = []
    for row in _xml(raw).findall("position"):
        identity, title = _text(row, "id"), _text(row, "name")
        chunks = []
        for section in row.findall("./jobDescriptions/jobDescription"):
            chunks.extend([_text(section, "name"), strip_html(_text(section, "value"))])
        description = "\n\n".join(c for c in chunks if c)
        if not identity or not title or not description:
            continue
        places = [_text(row, "office")]
        places.extend("".join(n.itertext()).strip() for n in row.findall("./additionalOffices/office"))
        jobs.append(Job(job_id=f"personio:{urlsplit(base).hostname}:{identity}", ats="personio",
                        company=company, title=title, location="; ".join(dict.fromkeys(p for p in places if p)),
                        url=f"{base}/job/{identity}?language=en", description=description,
                        posted_at=_text(row, "createdAt") or None))
    return _merge(jobs)


def fetch_personio(slug: str, company: str | None = None, session=None) -> list[Job]:
    base = origin(slug, "jobs.personio.de") if "jobs.personio.com" not in slug else origin(slug, "jobs.personio.com")
    response = _response(session or requests.Session(), f"{base}/xml", params={"language": "en"})
    return parse_personio(slug, company or slug, response.content)


def parse_teamtailor(slug: str, company: str, raw: bytes | str) -> list[Job]:
    base = origin(slug, "teamtailor.com")
    jobs = []
    for item in _xml(raw).findall("./channel/item"):
        identity, title, link = _text(item, "guid"), _text(item, "title"), _text(item, "link")
        description = strip_html(_text(item, "description"))
        if not identity or not title or not link or not description:
            continue
        places = []
        for loc in item.findall("./tt:locations/tt:location", TT):
            parts = [loc.findtext("tt:name", "", TT), loc.findtext("tt:country", "", TT)]
            places.append(", ".join(dict.fromkeys(p for p in parts if p)))
        if _text(item, "remoteStatus") in ("fully", "fully_remote"):
            places.append("Remote")
        posted = None
        try:
            posted = parsedate_to_datetime(_text(item, "pubDate")).isoformat()
        except (TypeError, ValueError):
            pass
        jobs.append(Job(job_id=f"teamtailor:{urlsplit(base).hostname}:{identity}", ats="teamtailor",
                        company=company, title=title, location="; ".join(dict.fromkeys(places)),
                        url=link, description=description, posted_at=posted))
    return _merge(jobs)


def fetch_teamtailor(slug: str, company: str | None = None, session=None) -> list[Job]:
    base = origin(slug, "teamtailor.com")
    session = session or requests.Session()
    jobs, seen = [], set()
    offset = 0
    for _ in range(MAX_PAGES):
        try:
            response = _response(session, f"{base}/jobs.rss", params={"per_page": PAGE_SIZE, "offset": offset})
            root = _xml(response.content)
            page = parse_teamtailor(slug, company or slug, response.content)
        except (requests.RequestException, ValueError, ET.ParseError) as exc:
            print(f"  ! teamtailor/{slug}: feed offset {offset} failed ({type(exc).__name__})")
            break
        count = len(root.findall("./channel/item"))
        new = [job for job in page if job.job_id not in seen]
        jobs.extend(new); seen.update(job.job_id for job in new)
        if count < PAGE_SIZE:
            break
        if not new:
            print(f"  ! teamtailor/{slug}: repeated page; stopped pagination")
            break
        offset += count
        time.sleep(REQUEST_DELAY)
    else:
        print(f"  ! teamtailor/{slug}: stopped at {MAX_PAGES} pages; board may be incomplete")
    return jobs


def parse_pinpoint(slug: str, company: str, body: dict) -> list[Job]:
    base = origin(slug, "pinpointhq.com")
    jobs = []
    for row in body.get("data") or []:
        identity, title, link = row.get("id"), row.get("title"), row.get("url")
        description = "\n\n".join(strip_html(row.get(key)) for key in
            ("description", "key_responsibilities", "skills_knowledge_expertise", "benefits") if row.get(key))
        if not identity or not title or not link or not description:
            continue
        loc = row.get("location") or {}
        location = ", ".join(dict.fromkeys(str(loc[k]) for k in ("city", "name") if loc.get(k)))
        if row.get("workplace_type") in ("remote", "fully_remote"):
            location = f"{location}; Remote" if location else "Remote"
        jobs.append(Job(job_id=f"pinpoint:{urlsplit(base).hostname}:{identity}", ats="pinpoint",
                        company=company, title=title.strip(), location=location, url=link,
                        description=description, posted_at=row.get("published_at") or row.get("created_at")))
    return _merge(jobs)


def fetch_pinpoint(slug: str, company: str | None = None, session=None) -> list[Job]:
    base = origin(slug, "pinpointhq.com")
    response = _response(session or requests.Session(), f"{base}/postings.json")
    return parse_pinpoint(slug, company or slug, response.json())


class CareerHTML(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []; self.scripts = []; self._script = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self._script = []

    def handle_data(self, data):
        if self._script is not None: self._script.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._script is not None:
            self.scripts.append("".join(self._script)); self._script = None


def _jobposting(node):
    if isinstance(node, list):
        for child in node: yield from _jobposting(child)
    elif isinstance(node, dict):
        kind = node.get("@type", [])
        if kind == "JobPosting" or isinstance(kind, list) and "JobPosting" in kind:
            yield node
        yield from _jobposting(node.get("@graph", []))


def parse_jobposting(ats: str, slug: str, company: str, identity: str,
                     url: str, raw: str) -> list[Job]:
    html = CareerHTML(); html.feed(raw)
    for script in html.scripts:
        try:
            nodes = list(_jobposting(json.loads(script)))
        except (ValueError, TypeError):
            continue
        for node in nodes:
            description = strip_html(node.get("description"))
            if not node.get("title") or not description:
                continue
            expiry = node.get("validThrough")
            if expiry:
                try:
                    dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                    if dt.replace(tzinfo=dt.tzinfo or timezone.utc) < datetime.now(timezone.utc): continue
                except (ValueError, TypeError):
                    pass
            places = []
            locations = node.get("jobLocation") or []
            if isinstance(locations, dict): locations = [locations]
            for loc in locations:
                address = loc.get("address") or {}
                country = address.get("addressCountry")
                if isinstance(country, dict): country = country.get("name")
                parts = [address.get("addressLocality"), address.get("addressRegion"), country]
                places.append(", ".join(str(p) for p in parts if p))
            if node.get("jobLocationType") == "TELECOMMUTE": places.append("Remote")
            restrictions = node.get("applicantLocationRequirements") or []
            if isinstance(restrictions, dict): restrictions = [restrictions]
            places.extend(loc.get("name", "") for loc in restrictions)
            return [Job(job_id=f"{ats}:{slug}:{identity}", ats=ats, company=company,
                        title=node["title"].strip(), location="; ".join(dict.fromkeys(p for p in places if p)),
                        url=url, description=description, posted_at=node.get("datePosted"))]
    return []


def _details(ats: str, slug: str, company: str, links: list[tuple[str, str]], session) -> list[Job]:
    jobs = []
    if len(links) > MAX_DETAILS:
        print(f"  ! {ats}/{slug}: detail cap {MAX_DETAILS} reached; board may be incomplete")
    for identity, url in links[:MAX_DETAILS]:
        time.sleep(REQUEST_DELAY)
        try:
            response = _response(session, url)
            parsed = parse_jobposting(ats, slug, company, identity, url, response.text)
            jobs.extend(parsed)
            if not parsed: print(f"  ! {ats}/{slug}: no usable JobPosting metadata for {identity}")
        except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
            print(f"  ! {ats}/{slug}: detail {identity} skipped ({type(exc).__name__})")
    return _merge(jobs)


def fetch_breezy(slug: str, company: str | None = None, session=None) -> list[Job]:
    validate_slug(slug)
    base = origin(slug, "breezy.hr"); session = session or requests.Session()
    rows = _response(session, f"{base}/json").json()
    links = {}
    for row in rows:
        identity, url = row.get("id"), row.get("url") or ""
        if identity and url.startswith(f"{base}/p/"):
            links[str(identity)] = url
    return _details("breezy", slug, company or slug, list(links.items()), session)


def fetch_jobvite(slug: str, company: str | None = None, session=None) -> list[Job]:
    validate_slug(slug)
    base = f"https://jobs.jobvite.com/{slug}"
    session = session or requests.Session()
    response = _response(session, f"{base}/jobs")
    html = CareerHTML(); html.feed(response.text)
    links = {}
    for href in html.links:
        url = urljoin(f"{base}/jobs", href)
        path = urlsplit(url)
        match = re.fullmatch(rf"/{re.escape(slug)}/job/([A-Za-z0-9_-]+)", path.path)
        if path.scheme == "https" and path.netloc == "jobs.jobvite.com" and match:
            links[match.group(1)] = f"{base}/job/{match.group(1)}"
    if not links:
        print(f"  ! jobvite/{slug}: no visible job links; board may be empty or use a different layout")
    return _details("jobvite", slug, company or slug, list(links.items()), session)
