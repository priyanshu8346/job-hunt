"""Public ATS schemas and transports; all HTTP is stubbed."""
from copy import deepcopy
from datetime import datetime

import pytest
import requests

from jobhunt.boards import (
    fetch_recruitee, fetch_smartrecruiters, parse_recruitee,
    parse_smartrecruiters, parse_workable, validate_slug,
)
from jobhunt.fetch import fetch_all, fetch_board
from jobhunt.prefilter import _parse_date


def smart(identity="123"):
    return {"id": identity, "name": "Frontend Engineer", "active": True,
            "visibility": "PUBLIC", "releasedDate": "2026-10-15T00:00:00Z",
            "postingUrl": f"https://jobs.smartrecruiters.com/Example/{identity}",
            "location": {"city": "Bengaluru", "country": "in", "remote": True},
            "jobAd": {"sections": {
                "companyDescription": {"text": "<p>About us</p>"},
                "jobDescription": {"text": "<p>Build React &amp; TypeScript</p>"},
                "qualifications": {"text": "<p>2–4 years required</p>"},
                "additionalInformation": {"text": "<p>Visa requirements</p>"},
            }}}


def workable():
    return {"shortcode": "ABC123", "title": "Full Stack Engineer", "state": "Karnataka",
            "description": "<p>Build APIs</p>", "requirements": "<p>Node.js &amp; React</p>",
            "benefits": "<p>Paid leave</p>", "published_on": "2026-10-14",
            "created_at": "2020-01-01", "url": "https://apply.workable.com/j/ABC123",
            "city": "Bengaluru", "country": "India", "telecommuting": True,
            "locations": [{"city": "Bengaluru", "country": "India"}]}


def recruitee():
    return {"id": 77, "guid": "stable", "slug": "frontend-engineer", "status": "published",
            "title": "Frontend Engineer", "description": "<p>Build UI</p>",
            "requirements": "<p>TypeScript &amp; React</p>", "remote": True,
            "location": "Pune, India", "locations": [{"city": "Bengaluru", "country": "India"}],
            "published_at": "2026-10-15 08:22:05 UTC", "created_at": "2020-01-01 08:22:05 UTC",
            "careers_url": "https://example.recruitee.com/o/frontend-engineer"}


class Response:
    def __init__(self, body, status=200): self.body, self.status_code = body, status
    def raise_for_status(self):
        if self.status_code >= 400: raise requests.HTTPError(str(self.status_code), response=self)
    def json(self): return deepcopy(self.body)


class Session:
    def __init__(self, *responses): self.responses, self.calls = iter(responses), []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


@pytest.fixture(autouse=True)
def no_delay(monkeypatch): monkeypatch.setattr("jobhunt.boards.REQUEST_DELAY", 0)


def test_smart_full_description_qualifications_dates_and_location():
    job, = parse_smartrecruiters("Example", "Example Inc", smart())
    assert job.job_id == "smartrecruiters:Example:123"
    assert job.company == "Example Inc" and job.ats == "smartrecruiters"
    assert job.location == "Bengaluru, India; Remote"
    assert job.posted_at == "2026-10-15T00:00:00Z"
    for text in ["Build React & TypeScript", "2–4 years required", "Visa requirements", "About us"]:
        assert text in job.description
    assert job.description.index("2–4 years") < job.description.index("About us")
    assert job.url.endswith("/123")


@pytest.mark.parametrize("field,value", [("active", False), ("visibility", "PRIVATE"),
                                         ("id", None), ("name", "")])
def test_smart_skips_invalid_and_nonpublic_postings(field, value):
    body = smart(); body[field] = value
    assert parse_smartrecruiters("Example", "Example", body) == []


def test_smart_paginates_by_actual_page_size_and_fetches_details():
    session = Session(
        Response({"totalFound": 2, "content": [{"id": "1", "ref": "https://evil.test"}]}),
        Response(smart("1")),
        Response({"totalFound": 2, "content": [{"id": "2"}]}), Response(smart("2")),
    )
    jobs = fetch_board("smartrecruiters", "Example", "Example", session=session)
    assert len(jobs) == 2
    assert session.calls[0][1]["params"] == {"limit": 100, "offset": 0}
    assert session.calls[2][1]["params"]["offset"] == 1
    assert session.calls[1][0] == "https://api.smartrecruiters.com/v1/companies/Example/postings/1"
    assert all("evil.test" not in url for url, _ in session.calls)


def test_smart_failed_detail_does_not_hide_later_jobs():
    session = Session(Response({"totalFound": 2, "content": [{"id": "1"}, {"id": "2"}]}),
                      Response({}, 404), Response(smart("2")))
    assert [j.job_id for j in fetch_smartrecruiters("Example", session=session)] == ["smartrecruiters:Example:2"]


def test_smart_repeated_page_stops_without_duplicate_detail_requests():
    page = Response({"totalFound": 20, "content": [{"id": "1"}]})
    session = Session(page, Response(smart("1")), page)
    assert len(fetch_smartrecruiters("Example", session=session)) == 1
    assert len(session.calls) == 3


def test_smart_page_limit_warns(monkeypatch, capsys):
    monkeypatch.setattr("jobhunt.boards.MAX_PAGES", 1)
    session = Session(Response({"totalFound": 20, "content": [{"id": "1"}]}), Response(smart("1")))
    assert len(fetch_smartrecruiters("Example", session=session)) == 1
    assert "board may be incomplete" in capsys.readouterr().out


def test_workable_combines_description_and_duplicate_location_rows():
    first = workable(); second = workable()
    second['locations'] = [{"city": "Pune", "country": "India"}]
    job, = parse_workable("example", "Example", {"jobs": [first, second]})
    assert job.job_id == "workable:example:ABC123"
    assert "Bengaluru, India" in job.location and "Pune, India" in job.location
    assert job.location.count("Remote") == 1
    assert job.posted_at == "2026-10-14"
    assert "Node.js & React" in job.description and "Paid leave" in job.description


def test_workable_transport_requests_full_descriptions():
    session = Session(Response({"jobs": [workable()]}))
    assert len(fetch_board("workable", "example", session=session)) == 1
    assert session.calls[0][0] == "https://www.workable.com/api/accounts/example"
    assert session.calls[0][1]["params"] == {"details": "true"}


@pytest.mark.parametrize("state", [None, "", "Karnataka", "Tamil Nadu"])
def test_workable_state_is_a_location_not_a_publication_status(state):
    row = workable(); row["state"] = state
    assert len(parse_workable("example", "Example", {"jobs": [row]})) == 1


def test_recruitee_requirements_locations_and_parseable_publication_date():
    job, = parse_recruitee("example", "Example", {"offers": [recruitee()]})
    assert job.job_id == "recruitee:example:77"
    assert "Pune, India" in job.location and "Bengaluru, India" in job.location
    assert "TypeScript & React" in job.description
    assert _parse_date(job.posted_at).date() == datetime(2026, 10, 15).date()
    renamed = recruitee(); renamed["slug"] = "renamed"
    assert parse_recruitee("example", "Example", {"offers": [renamed]})[0].job_id == job.job_id


@pytest.mark.parametrize("parser,key,factory", [
    (parse_workable, "jobs", workable),
    (parse_recruitee, "offers", recruitee),
])
def test_incomplete_jobs_skipped(parser,key,factory):
    incomplete = factory(); incomplete["description"] = ""; incomplete["requirements"] = ""; incomplete["benefits"] = ""
    assert parser("example", "Example", {key: [incomplete]}) == []
    assert parser("example", "Example", {}) == []


def test_recruitee_closed_jobs_skipped():
    closed = recruitee(); closed["status"] = "closed"
    assert parse_recruitee("example", "Example", {"offers": [closed]}) == []


def test_recruitee_uses_only_matching_employer_token(monkeypatch):
    monkeypatch.setenv("RECRUITEE_CAREERS_TOKEN_EXAMPLE", "test-token")
    monkeypatch.setenv("RECRUITEE_CAREERS_TOKEN_OTHER", "other-token")
    session = Session(Response({"offers": [recruitee()]}))
    assert len(fetch_recruitee("example", session=session)) == 1
    assert session.calls[0][1]["headers"]["X-Careers-Sites-Token"] == "test-token"
    monkeypatch.delenv("RECRUITEE_CAREERS_TOKEN_EXAMPLE")
    session = Session(Response({"offers": []}))
    fetch_recruitee("example", session=session)
    assert "X-Careers-Sites-Token" not in session.calls[0][1]["headers"]


def test_recruitee_auth_requirement_logged_without_token_leak(monkeypatch, capsys):
    monkeypatch.setenv("RECRUITEE_CAREERS_TOKEN_EXAMPLE", "private-test-token")
    assert fetch_recruitee("example", session=Session(Response({}, 401))) == []
    log = capsys.readouterr().out
    assert "RECRUITEE_CAREERS_TOKEN_EXAMPLE" in log and "private-test-token" not in log


@pytest.mark.parametrize("slug", ["https://example.com", "../escape", "foo/bar", "foo?key=1", ""])
def test_company_identifiers_validated(slug):
    with pytest.raises(ValueError): validate_slug(slug)


@pytest.mark.parametrize("ats", ["smartrecruiters", "workable", "recruitee"])
def test_fetch_all_dispatches_new_platforms(monkeypatch, ats):
    calls=[]
    def fake(slug, company, session=None): calls.append((slug,company)); return []
    monkeypatch.setattr(f"jobhunt.boards.fetch_{ats}", fake)
    assert fetch_all([{"ats":ats,"slug":"example","name":"Example"}],sleep=0) == []
    assert calls == [("example","Example")]
