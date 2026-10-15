"""Workday transport and parsing checks; no live API calls or credentials."""
from copy import deepcopy

import pytest
import requests

from jobhunt.fetch import fetch_all, fetch_board
from jobhunt.workday import board_parts, fetch_workday, parse_workday

BOARD = "https://example.wd108.myworkdayjobs.com/en-US/careers"


def detail(req="JR123"):
    return {"jobPostingInfo": {
        "id": "internal-id", "jobReqId": req,
        "title": "Frontend Engineer", "location": "Bengaluru",
        "additionalLocations": ["Pune", {"descriptor": "Hyderabad"}, "Pune"],
        "country": {"descriptor": "India"}, "startDate": "2026-10-01",
        "postedOn": "Posted 14 Days Ago",
        "externalUrl": f"https://example.wd108.myworkdayjobs.com/careers/job/India/Frontend_{req}",
        "jobDescription": "<p>Build React &amp; TypeScript.</p><ul><li>2–4 years.</li></ul>",
    }}


class Response:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return deepcopy(self.body)


class Session:
    def __init__(self, pages, details):
        self.pages, self.details = iter(pages), details
        self.posts, self.gets = [], []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return next(self.pages)

    def get(self, url, **kwargs):
        self.gets.append(url)
        return self.details[url.rsplit("/", 1)[-1]]


@pytest.fixture(autouse=True)
def no_delay(monkeypatch):
    monkeypatch.setattr("jobhunt.workday.REQUEST_DELAY", 0)


def test_full_description_date_locations_and_stable_identity():
    job, = parse_workday(BOARD, "Example", detail())
    assert job.job_id == "workday:example:careers:JR123"
    assert job.ats == "workday" and job.company == "Example"
    assert "Build React & TypeScript." in job.description
    assert "2–4 years." in job.description and "<li>" not in job.description
    assert job.location == "Bengaluru; Pune; Hyderabad; India"
    assert job.posted_at == "2026-10-01"
    assert job.url.endswith("Frontend_JR123")
    changed = detail(); changed["jobPostingInfo"]["title"] = "Updated title"
    assert parse_workday(BOARD, "Example", changed)[0].job_id == job.job_id


@pytest.mark.parametrize("url", [
    BOARD, "https://example.wd108.myworkdayjobs.com/careers",
    "https://example.myworkdayjobs.com/en-US/careers/",
])
def test_board_url_with_or_without_locale(url):
    origin, tenant, site = board_parts(url)
    assert origin.startswith("https://example.")
    assert (tenant, site) == ("example", "careers")


@pytest.mark.parametrize("url", [
    "http://example.wd1.myworkdayjobs.com/careers",
    "https://example.wd1.myworkdayjobs.com.evil.test/careers",
    "https://user:pass@example.wd1.myworkdayjobs.com/careers",
    "https://example.wd1.myworkdayjobs.com:9999/careers",
    "https://example.wd1.myworkdayjobs.com/en-US/careers/job/123",
    "https://example.wd1.myworkdayjobs.com/",
])
def test_invalid_board_urls_rejected_before_network(url):
    with pytest.raises(ValueError):
        board_parts(url)


def test_missing_detail_not_misrepresented_as_a_job():
    assert parse_workday(BOARD, "Example", {}) == []
    body = detail(); del body["jobPostingInfo"]["jobDescription"]
    assert parse_workday(BOARD, "Example", body) == []


def test_pagination_handles_short_pages_and_fetches_full_details():
    session = Session([
        Response({"total": 2, "jobPostings": [{"externalPath": "/job/India/A"}]}),
        Response({"total": 2, "jobPostings": [{"externalPath": "/job/India/B"}]}),
    ], {"A": Response(detail("A")), "B": Response(detail("B"))})
    jobs = fetch_board("workday", BOARD, "Example", session=session)
    assert len(jobs) == 2
    assert [call[1]["json"]["offset"] for call in session.posts] == [0, 1]
    assert all(call[1]["json"]["limit"] == 20 for call in session.posts)
    assert session.posts[0][0].endswith("/wday/cxs/example/careers/jobs")
    assert all("/wday/cxs/example/careers/job/India/" in url for url in session.gets)


def test_repeated_page_does_not_loop_or_duplicate_jobs():
    page = Response({"total": 50, "jobPostings": [{"externalPath": "/job/India/A"}]})
    session = Session([page, page], {"A": Response(detail())})
    assert len(fetch_workday(BOARD, session=session)) == 1
    assert len(session.posts) == 2 and len(session.gets) == 1


def test_failed_detail_skipped_and_later_job_still_loaded():
    page = Response({"total": 2, "jobPostings": [
        {"externalPath": "/job/India/A"}, {"externalPath": "/job/India/B"}]})
    session = Session([page], {"A": Response({}, 404), "B": Response(detail("B"))})
    assert [j.job_id for j in fetch_workday(BOARD, session=session)] == ["workday:example:careers:B"]


def test_later_list_failure_preserves_already_fetched_jobs():
    session = Session([
        Response({"total": 50, "jobPostings": [{"externalPath": "/job/India/A"}]}),
        Response({}, 503),
    ], {"A": Response(detail())})
    assert len(fetch_workday(BOARD, session=session)) == 1


def test_empty_or_inaccessible_board_returns_no_jobs():
    assert fetch_workday(BOARD, session=Session([Response({"jobPostings": []})], {})) == []
    assert fetch_workday(BOARD, session=Session([Response({}, 403)], {})) == []


def test_fetch_all_routes_workday_with_existing_board_format(monkeypatch):
    expected = parse_workday(BOARD, "Example", detail())
    calls = []
    def fake(url, company, session=None):
        calls.append((url, company)); return expected
    monkeypatch.setattr("jobhunt.workday.fetch_workday", fake)
    assert fetch_all([{"ats": "workday", "slug": BOARD, "name": "Example"}], sleep=0) == expected
    assert calls == [(BOARD, "Example")]
