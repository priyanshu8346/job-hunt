"""Additional public feed schemas and advertised JobPosting metadata."""
import json

import pytest
import requests

from jobhunt.fetch import fetch_board
from jobhunt.public_boards import (
    CareerHTML, origin, parse_personio, parse_teamtailor, parse_pinpoint,
    parse_jobposting, fetch_teamtailor, fetch_breezy, fetch_jobvite,
)

PERSONIO = b'''<workzag-jobs><position><id>42</id><name>Frontend Engineer</name>
<office>Bengaluru</office><additionalOffices><office>Pune</office></additionalOffices>
<createdAt>2026-10-01T12:00:00+00:00</createdAt><jobDescriptions>
<jobDescription><name>Responsibilities</name><value><![CDATA[<p>Build React &amp; TypeScript</p>]]></value></jobDescription>
<jobDescription><name>Requirements</name><value><![CDATA[<p>2-4 years</p>]]></value></jobDescription>
</jobDescriptions></position></workzag-jobs>'''


def rss(identity="stable-id"):
    return f'''<rss xmlns:tt="https://teamtailor.com/locations"><channel><item>
<guid>{identity}</guid><title>Backend Engineer</title><description>&lt;p&gt;Node.js APIs&lt;/p&gt;</description>
<pubDate>Thu, 15 Oct 2026 08:00:00 +0530</pubDate><link>https://example.teamtailor.com/jobs/123</link>
<remoteStatus>fully</remoteStatus><tt:locations><tt:location><tt:name>Bengaluru</tt:name>
<tt:country>India</tt:country></tt:location></tt:locations></item></channel></rss>'''.encode()


def posting(**updates):
    node = {"@type":"JobPosting", "title":"Full Stack Engineer", "description":"<p>React &amp; Node</p>",
            "datePosted":"2026-10-15", "jobLocation":[{"address":{"addressLocality":"Bengaluru", "addressCountry":"India"}}]}
    node.update(updates)
    return node


def page(node):
    return '<script type="application/ld+json">'+json.dumps(node)+'</script>'


class Response:
    def __init__(self,body,status=200):
        self.body,self.status_code=body,status
        self.text=body if isinstance(body,str) else ""
        self.content=body if isinstance(body,bytes) else self.text.encode()
    def json(self):return self.body
    def raise_for_status(self):
        if self.status_code>=400:raise requests.HTTPError(str(self.status_code),response=self)


class Session:
    def __init__(self,*responses):self.responses=iter(responses);self.calls=[]
    def get(self,url,**kwargs):self.calls.append((url,kwargs));return next(self.responses)


@pytest.fixture(autouse=True)
def no_delay(monkeypatch):monkeypatch.setattr("jobhunt.public_boards.REQUEST_DELAY",0)


def test_personio_full_sections_extra_offices_and_real_date():
    job,=parse_personio("example","Example",PERSONIO)
    assert job.job_id=="personio:example.jobs.personio.de:42"
    assert job.location=="Bengaluru; Pune"
    assert "Build React & TypeScript" in job.description and "2-4 years" in job.description
    assert job.posted_at=="2026-10-01T12:00:00+00:00"
    assert job.url=="https://example.jobs.personio.de/job/42?language=en"


def test_personio_dot_com_and_unknown_date():
    job,=parse_personio("https://example.jobs.personio.com","Example",PERSONIO.replace(
        b'<createdAt>2026-10-01T12:00:00+00:00</createdAt>',b''))
    assert job.posted_at is None and job.url.startswith("https://example.jobs.personio.com/")


@pytest.mark.parametrize("parser,slug",[(parse_personio,"example"),(parse_teamtailor,"example")])
def test_xml_entity_declarations_rejected(parser,slug):
    with pytest.raises(ValueError):parser(slug,"Example",'<!DOCTYPE a [<!ENTITY x "unsafe">]><a/>')


def test_teamtailor_namespace_remote_and_rfc_date():
    job,=parse_teamtailor("example","Example",rss())
    assert job.job_id=="teamtailor:example.teamtailor.com:stable-id"
    assert job.location=="Bengaluru, India; Remote"
    assert job.posted_at=="2026-10-15T08:00:00+05:30"
    assert job.description=="Node.js APIs"


def test_teamtailor_paginates_and_stops_repeated_pages(monkeypatch):
    monkeypatch.setattr("jobhunt.public_boards.PAGE_SIZE",1)
    session=Session(Response(rss()),Response(rss()))
    assert len(fetch_teamtailor("example",session=session))==1
    assert [kwargs['params']['offset'] for _,kwargs in session.calls]==[0,1]


def test_teamtailor_later_failure_preserves_jobs(monkeypatch):
    monkeypatch.setattr("jobhunt.public_boards.PAGE_SIZE",1)
    session=Session(Response(rss()),Response(b"",503))
    assert len(fetch_teamtailor("example",session=session))==1


def test_pinpoint_preserves_requirements_without_inventing_date():
    row={"id":"1","title":"SDE I - Backend","description":"<p>Build APIs</p>",
         "key_responsibilities":"<p>Own releases</p>","skills_knowledge_expertise":"<p>Node.js</p>",
         "benefits":"<p>Benefits</p>","url":"https://example.pinpointhq.com/en/postings/abc",
         "location":{"city":"Bengaluru","name":"India"},"workplace_type":"remote"}
    job,=parse_pinpoint("example","Example",{"data":[row]})
    assert job.job_id=="pinpoint:example.pinpointhq.com:1"
    assert all(s in job.description for s in ["Build APIs","Own releases","Node.js","Benefits"])
    assert job.posted_at is None and "India" in job.location and "Remote" in job.location


def test_jobposting_graph_multiple_scripts_and_restrictions():
    raw=page({"@type":"WebSite"})+page({"@graph":[posting(jobLocationType="TELECOMMUTE",
        applicantLocationRequirements=[{"name":"India"}])]})
    job,=parse_jobposting("breezy","example","Example","stable","https://example.breezy.hr/p/stable",raw)
    assert job.job_id=="breezy:example:stable"
    assert "India" in job.location and "Remote" in job.location
    assert job.description=="React & Node" and job.posted_at=="2026-10-15"


def test_jobposting_expired_or_missing_description_skipped():
    args=("breezy","example","Example","stable","https://example.breezy.hr/p/stable")
    assert parse_jobposting(*args,page(posting(validThrough="2000-01-01")))==[]
    assert parse_jobposting(*args,page(posting(description="")))==[]
    assert parse_jobposting(*args,'<script type="application/ld+json">broken</script>')==[]


def test_breezy_only_fetches_same_board_details_and_deduplicates():
    row={"id":"1","url":"https://example.breezy.hr/p/1-role"}
    session=Session(Response([row,row,{"id":"bad","url":"https://evil.test/p/bad"}]),Response(page(posting())))
    jobs=fetch_breezy("example",session=session)
    assert len(jobs)==1 and len(session.calls)==2
    assert jobs[0].job_id=="breezy:example:1"


def test_jobvite_discovers_visible_jobs_and_isolates_detail_failure():
    listing='<a href="/example/job/one">One</a><a href="/example/job/two">Two</a>'
    listing+='<a href="https://evil.test/example/job/three">bad</a>'
    session=Session(Response(listing),Response("",404),Response(page(posting())))
    jobs=fetch_jobvite("example",session=session)
    assert [j.job_id for j in jobs]==["jobvite:example:two"]
    assert len(session.calls)==3


@pytest.mark.parametrize("slug",["https://evil.test","https://example.teamtailor.com.evil.test",
    "https://user:pass@example.teamtailor.com","https://example.teamtailor.com/jobs"])
def test_feed_origins_cannot_change_to_arbitrary_hosts(slug):
    with pytest.raises(ValueError):origin(slug,"teamtailor.com")


@pytest.mark.parametrize("ats",["personio","teamtailor","pinpoint","breezy","jobvite"])
def test_fetch_board_dispatches_platform(monkeypatch,ats):
    calls=[]
    def fake(slug,company,session=None):calls.append((slug,company));return []
    monkeypatch.setattr(f"jobhunt.public_boards.fetch_{ats}",fake)
    assert fetch_board(ats,"example","Example")==[]
    assert calls==[("example","Example")]
