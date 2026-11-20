from pathlib import Path

import httpx
import pytest

from src.miners import orchestrator
from src.miners.ashby import mine_ashby
from src.miners.base import (
    clean_html,
    format_salary_range,
    is_location_eligible,
    make_deterministic_id,
    normalize_contract_type,
)
from src.miners.github_br import mine_github_brasil
from src.miners.greenhouse import mine_greenhouse
from src.miners.hackernews import mine_hackernews
from src.miners.http_client import DiskHTTPCache, DomainRateLimiter, ResilientHTTPClient
from src.miners.jobicy import mine_jobicy
from src.miners.lever import mine_lever
from src.miners.remotive import mine_remotive
from src.miners.weworkremotely import mine_weworkremotely


def _make_client(tmp_path: Path, handler) -> ResilientHTTPClient:
    return ResilientHTTPClient(
        max_retries=0,
        use_cache=False,
        cache=DiskHTTPCache(cache_dir=tmp_path / "cache"),
        rate_limiter=DomainRateLimiter(default_interval=0.0, per_domain={}),
        transport=httpx.MockTransport(handler),
    )


def test_base_helpers_html_id_contract_salary_and_location():
    double_escaped = "&lt;p&gt;Hello &amp;amp; Python&lt;/p&gt;&lt;br/&gt;&lt;li&gt;Async&lt;/li&gt;"
    assert clean_html(double_escaped) == "Hello & Python Async"
    assert "\n" in clean_html(double_escaped, preserve_newlines=True)

    assert make_deterministic_id("wwr", "https://example.com/1") == make_deterministic_id(
        "wwr", "https://example.com/1"
    )
    assert normalize_contract_type(["Part-Time", "Contractor"]) == "Part-Time, Contractor"
    assert normalize_contract_type("['Part-Time']") == "Part-Time"
    assert format_salary_range("", "", "USD") == "Não informado"
    assert format_salary_range(80000, 120000, "USD") == "80000-120000 USD"

    assert is_location_eligible("Worldwide") is True
    assert is_location_eligible("LATAM, Europe, USA") is True
    assert is_location_eligible("Brazil") is True
    assert is_location_eligible("USA") is False
    assert is_location_eligible("Austria") is False
    assert is_location_eligible("San Francisco, CA") is False
    assert is_location_eligible("Anywhere in the US") is False
    assert is_location_eligible("Remote", "Must be located in the United States only.") is False
    assert is_location_eligible("Worldwide", "Open globally excluding Brazil.") is False


def test_remotive_and_jobicy_miners_sanitize_data(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "remotive.com" in url:
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": 101,
                            "company_name": "AsyncCo",
                            "title": "Python Engineer",
                            "candidate_required_location": "Worldwide",
                            "job_type": "contract",
                            "salary": "$70k",
                            "url": "https://remotive.com/jobs/101",
                            "publication_date": "2026-11-18T10:00:00",
                            "description": "<p>Async Python &amp; FastAPI</p>",
                        },
                        {
                            "id": 102,
                            "company_name": "USOnly",
                            "title": "Python Dev",
                            "candidate_required_location": "USA Only",
                            "url": "https://remotive.com/jobs/102",
                            "description": "<p>US only</p>",
                        },
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 201,
                        "companyName": "LatamTech",
                        "jobTitle": "Automation Engineer",
                        "jobGeo": "LATAM",
                        "jobType": ["Part-Time"],
                        "annualSalaryMin": "",
                        "annualSalaryMax": "",
                        "salaryCurrency": "USD",
                        "url": "https://jobicy.com/jobs/201",
                        "pubDate": "2026-11-19",
                        "jobDescription": "<p>Python Playwright async</p>",
                    },
                    {
                        "id": 202,
                        "companyName": "AustriaCorp",
                        "jobTitle": "Backend",
                        "jobGeo": "Austria",
                        "url": "https://jobicy.com/jobs/202",
                        "jobDescription": "<p>Python</p>",
                    },
                ]
            },
        )

    with _make_client(tmp_path, handler) as client:
        rem = mine_remotive(client=client)
        job = mine_jobicy(client=client)

    assert len(rem) == 1
    assert rem[0]["id"] == "remotive_101"
    assert rem[0]["descricao"] == "Async Python & FastAPI"

    assert len(job) == 1
    assert job[0]["tipo_contrato"] == "Part-Time"
    assert job[0]["salario"] == "Não informado"


def test_weworkremotely_and_github_br_miners(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token")
    seen_auth: list[str] = []

    rss_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <item>
        <title>RemoteCorp: Python Scraper</title>
        <link>https://weworkremotely.com/remote-jobs/remotecorp-python</link>
        <pubDate>Thu, 19 Nov 2026</pubDate>
        <region>Worldwide</region>
        <description>&lt;p&gt;Async Playwright &amp;amp; Docker&lt;/p&gt;</description>
      </item>
    </channel></rss>"""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "weworkremotely.com" in url:
            return httpx.Response(200, content=rss_xml)
        if "api.github.com" in url:
            seen_auth.append(request.headers.get("Authorization", ""))
            return httpx.Response(
                200,
                json=[
                    {"id": 1, "title": "PR", "pull_request": {}, "body": "Remoto"},
                    {"id": 2, "title": "[Presencial] Dev Java", "body": "São Paulo", "labels": []},
                    {
                        "id": 3,
                        "title": "[Remoto] Desenvolvedor Python PJ",
                        "body": "Python, FastAPI e Docker 100% remoto.",
                        "labels": [{"name": "Remoto"}],
                        "html_url": "https://github.com/backend-br/vagas/issues/3",
                        "created_at": "2026-11-18T12:00:00Z",
                    },
                ],
            )
        return httpx.Response(404)

    with _make_client(tmp_path, handler) as client:
        wwr = mine_weworkremotely(client=client)
        gh = mine_github_brasil(client=client)

    assert len(wwr) >= 1
    assert wwr[0]["id"] == make_deterministic_id("wwr", "https://weworkremotely.com/remote-jobs/remotecorp-python")
    assert wwr[0]["empresa"] == "RemoteCorp"

    assert seen_auth and seen_auth[0] == "Bearer ghp_test_token"
    assert len(gh) == 2  # dois repos retornando a mesma issue mockada
    assert gh[0]["id"] == "gh_3"


def test_ats_miners_greenhouse_ashby_lever(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "boards-api.greenhouse.io" in url:
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": 5001,
                            "title": "Senior Python Engineer",
                            "company_name": "GitLab",
                            "location": {"name": "Remote - Americas / LATAM"},
                            "absolute_url": "https://boards.greenhouse.io/gitlab/jobs/5001",
                            "updated_at": "2026-11-18T00:00:00Z",
                            "content": "&lt;p&gt;Async-first Python &amp;amp; Docker.&lt;/p&gt;",
                            "metadata": [{"name": "Employment Type", "value": "Contractor"}],
                        },
                        {
                            "id": 5002,
                            "title": "Office Manager",
                            "company_name": "GitLab",
                            "location": {"name": "San Francisco, CA"},
                            "absolute_url": "https://boards.greenhouse.io/gitlab/jobs/5002",
                            "content": "&lt;p&gt;On-site in SF&lt;/p&gt;",
                        },
                    ]
                },
            )
        if "api.ashbyhq.com" in url:
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {
                            "id": "ash-1",
                            "title": "Automation Engineer",
                            "isListed": True,
                            "isRemote": True,
                            "workplaceType": "Remote",
                            "location": "Remote",
                            "secondaryLocations": [{"location": "Worldwide"}],
                            "employmentType": "FullTime",
                            "publishedAt": "2026-11-17T08:00:00Z",
                            "jobUrl": "https://jobs.ashbyhq.com/posthog/ash-1",
                            "descriptionPlain": "Python, Playwright and async workflow.",
                            "compensation": {"compensationTierSummary": "$120K - $150K USD"},
                        },
                        {
                            "id": "ash-2",
                            "title": "Unlisted Role",
                            "isListed": False,
                            "isRemote": True,
                            "location": "Worldwide",
                        },
                        {
                            "id": "ash-3",
                            "title": "SF Onsite",
                            "isListed": True,
                            "isRemote": False,
                            "workplaceType": "OnSite",
                            "location": "San Francisco, CA",
                        },
                    ]
                },
            )
        if "api.lever.co" in url:
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "lev-1",
                        "text": "Python ETL Engineer",
                        "workplaceType": "remote",
                        "categories": {
                            "commitment": "Contract",
                            "location": "Remote - Worldwide",
                        },
                        "createdAt": 1763510400000,
                        "descriptionPlain": "Async contractor using Python and PostgreSQL.",
                        "lists": [{"text": "Stack", "content": "<ul><li>Docker</li><li>SQL</li></ul>"}],
                        "salaryRange": {"min": 80000, "max": 110000, "currency": "USD"},
                        "hostedUrl": "https://jobs.lever.co/toptal/lev-1",
                    },
                    {
                        "id": "lev-2",
                        "text": "Hybrid Designer",
                        "workplaceType": "hybrid",
                        "categories": {"location": "London"},
                        "descriptionPlain": "Hybrid in London",
                    },
                ],
            )
        return httpx.Response(404)

    with _make_client(tmp_path, handler) as client:
        ghb = mine_greenhouse(companies=["gitlab"], client=client)
        ash = mine_ashby(companies=["posthog"], client=client)
        lev = mine_lever(companies=["toptal"], client=client)

    assert len(ghb) == 1
    assert ghb[0]["id"] == "ghb_gitlab_5001"
    assert ghb[0]["tipo_contrato"] == "Contractor"
    assert ghb[0]["descricao"] == "Async-first Python & Docker."

    assert len(ash) == 1
    assert ash[0]["id"] == "ashby_posthog_ash-1"
    assert ash[0]["salario"] == "$120K - $150K USD"
    assert "Worldwide" in ash[0]["localizacao"]

    assert len(lev) == 1
    assert lev[0]["id"] == "lever_toptal_lev-1"
    assert lev[0]["salario"] == "80000-110000 USD"
    assert "Docker SQL" in lev[0]["descricao"]
    assert lev[0]["data_publicacao"].startswith("2025-11")


def test_hackernews_who_is_hiring_miner(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if "author_whoishiring" in params.get("tags", ""):
            return httpx.Response(
                200,
                json={
                    "hits": [
                        {
                            "objectID": "999000",
                            "title": "Ask HN: Who is hiring? (November 2026)",
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "objectID": "1111",
                        "parent_id": 999000,
                        "created_at": "2026-11-02T17:00:00Z",
                        "comment_text": (
                            "AsyncCorp | Senior Python / Playwright Engineer | "
                            "Remote (Worldwide / LATAM) | $100k-$130k | Contractor"
                            "<p>We work async-first with Python and Docker.</p>"
                        ),
                    },
                    {
                        "objectID": "2222",
                        "parent_id": 1111,  # reply aninhada (deve ignorar)
                        "comment_text": "Remote Python reply",
                    },
                    {
                        "objectID": "3333",
                        "parent_id": 999000,
                        "comment_text": "USStartup | Backend | Remote (US Only) | $150k<p>Python</p>",
                    },
                ]
            },
        )

    with _make_client(tmp_path, handler) as client:
        hn = mine_hackernews(keywords=("remote", "python"), client=client)

    assert len(hn) == 1
    assert hn[0]["id"] == "hn_1111"
    assert hn[0]["empresa"] == "AsyncCorp"
    assert hn[0]["titulo"] == "Senior Python / Playwright Engineer"
    assert hn[0]["salario"] == "$100k-$130k"
    assert hn[0]["url"] == "https://news.ycombinator.com/item?id=1111"


def test_orchestrator_concurrency_dedup_short_skills_and_error_isolation(
    monkeypatch: pytest.MonkeyPatch,
):
    profile = {
        "candidato": {"nome": "Dev"},
        "competencias": {"principais": ["Python", "QA", "Docker", "SQL"]},
        "horario_trabalho_desejado": {"permite_reunioes_horario_comercial": False},
    }

    def broken_miner() -> list[dict]:
        raise RuntimeError("API offline")

    def fake_ghb() -> list[dict]:
        return [
            {
                "id": "ghb_1",
                "fonte": "Greenhouse (gitlab)",
                "origem": "Internacional (USD/EUR)",
                "empresa": "GitLab",
                "titulo": "QA Automation Engineer",
                "localizacao": "Worldwide",
                "tipo_contrato": "Contractor",
                "salario": "Não informado",
                "url": "https://example.com/job/1/",
                "descricao": "Async-first flexible hours QA engineer with Python, Docker and SQL.",
                "resumo": "Async QA",
            }
        ]

    def fake_hn() -> list[dict]:
        return [
            # Duplicata com barra final diferente
            {
                "id": "hn_dup",
                "fonte": "HackerNews",
                "origem": "Internacional (USD/EUR)",
                "empresa": "GitLab",
                "titulo": "QA Automation Engineer",
                "localizacao": "Worldwide",
                "tipo_contrato": "Contractor",
                "salario": "Não informado",
                "url": "https://example.com/job/1",
                "descricao": "Async-first flexible hours QA engineer with Python, Docker and SQL.",
                "resumo": "Async QA",
            }
        ]

    monkeypatch.setattr(orchestrator, "mine_greenhouse", fake_ghb)
    monkeypatch.setattr(orchestrator, "mine_ashby", broken_miner)
    monkeypatch.setattr(orchestrator, "mine_hackernews", fake_hn)

    results = orchestrator.mine_all_opportunities(
        profile,
        fontes=["greenhouse", "ashby", "hn"],
        min_schedule=50,
        min_stack=25,
    )

    assert len(results) == 1
    assert results[0]["id"] == "ghb_1"
    assert "qa" in results[0]["matches_stack"]
    assert results[0]["stack_score"] == 100
    assert results[0]["schedule_fit"]["classificacao_exibicao"] == "[COMPATÍVEL]"
