"""
Sheila's Automated Job Hunter
Source: Adzuna API (reliable, no blocking)
"""

import os
import re
import json
import time
import smtplib
import urllib.request
import urllib.parse
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
GMAIL_ADDRESS      = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
TO_EMAIL           = "shernandez520@gmail.com"

ADZUNA_APP_ID  = "c4bacdf2"
ADZUNA_APP_KEY = "c1103b4cf305eae5b3b777b2d7e81512"
USAJOBS_API_KEY = "h4UTqXIJr5vRYZmcMYw4/31S0hJ+Z3/CLoNapZYkrpY="

SEARCH_QUERIES = [
    "production artist",
    "creative operations",
    "workflow automation",
    "implementation analyst",
    "print production",
    "creative ops",
    "process automation",
    "graphic production",
    "automation specialist",
    "creative project manager",
]

PROFILE = """
Sheila Hernandez — Candidate Profile:
- 20+ years in promotional products industry (supplier AND distributor side)
- Production artist: vector cleanup, file prep, color separations, screen print/embroidery/sublimation/laser setup
- Workflow automation: Python, PowerShell, Make.com, Zapier, Adobe ExtendScript
- Implementation analyst: process design, systems implementation, cross-functional stakeholder management
- Built ArtCheck (artcheck.app) — live SaaS art file screening tool with organic traction
- Built FINALIZER — internal batch automation suite at national distributor
- Tools: Adobe Illustrator, Photoshop, InDesign, CorelDRAW, NetSuite, Streamlit, GitHub
- 5/5 performance review (Exceptional), April 2026
- Looking for: contract, full-time, OR temp-to-permanent remote work
- $55/hr contract or $55-75k+ salary full time
- Open to within 20 miles of Bradenton FL (34209) or fully remote
- Available immediately
"""


def search_adzuna(query: str) -> list[dict]:
    """Search Adzuna API — works reliably from servers."""
    eq = urllib.parse.quote(query)
    # Search US jobs, remote + Florida
    urls = [
        f"https://api.adzuna.com/v1/api/jobs/us/search/1?app_id={ADZUNA_APP_ID}&app_key={ADZUNA_APP_KEY}&results_per_page=5&what={eq}&where=remote&content-type=application/json",
        f"https://api.adzuna.com/v1/api/jobs/us/search/1?app_id={ADZUNA_APP_ID}&app_key={ADZUNA_APP_KEY}&results_per_page=5&what={eq}&where=Bradenton+FL&distance=20&content-type=application/json",
    ]
    jobs = []
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JobHunter/1.0"})
            with urllib.request.urlopen(req, timeout=12) as r:
                data = json.loads(r.read().decode("utf-8"))
            for item in data.get("results", []):
                title    = item.get("title", "")
                link     = item.get("redirect_url", "")
                company  = item.get("company", {}).get("display_name", "")
                location = item.get("location", {}).get("display_name", "")
                desc     = re.sub(r"<[^>]+>", " ", item.get("description", ""))
                desc     = re.sub(r"\s+", " ", desc).strip()[:300]
                salary_min = item.get("salary_min")
                salary_max = item.get("salary_max")
                salary_str = ""
                if salary_min and salary_max:
                    salary_str = f" | ${int(salary_min):,}–${int(salary_max):,}/yr"
                elif salary_min:
                    salary_str = f" | ${int(salary_min):,}+/yr"
                if title and link:
                    jobs.append({
                        "title": title,
                        "company": company,
                        "location": location,
                        "url": link,
                        "description": f"{desc}{salary_str}",
                        "source": "Adzuna"
                    })
        except Exception as e:
            print(f"Adzuna failed for '{query}': {e}")
        time.sleep(0.3)
    return jobs


def search_usajobs(query: str) -> list[dict]:
    """Search USAJobs with real API key."""
    try:
        eq = urllib.parse.quote(query)
        url = f"https://data.usajobs.gov/api/search?Keyword={eq}&RemoteIndicator=True&ResultsPerPage=5&SortField=OpenDate&SortDirection=Desc"
        req = urllib.request.Request(url, headers={
            "User-Agent": "shernandez520@gmail.com",
            "Authorization-Key": USAJOBS_API_KEY
        })
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode("utf-8"))
        jobs = []
        for item in data.get("SearchResult", {}).get("SearchResultItems", []):
            pos   = item.get("MatchedObjectDescriptor", {})
            title = pos.get("PositionTitle", "")
            link  = pos.get("PositionURI", "")
            org   = pos.get("OrganizationName", "")
            rem   = pos.get("PositionRemuneration", [{}])[0]
            pay   = f"${rem.get('MinimumRange','?')}–${rem.get('MaximumRange','?')} {rem.get('RateIntervalCode','')}"
            sched = pos.get("PositionScheduleType", [{}])[0].get("Name", "")
            close = pos.get("ApplicationCloseDate", "")[:10]
            if title and link:
                jobs.append({
                    "title": title,
                    "company": org,
                    "location": "Remote (Federal)",
                    "url": link,
                    "description": f"{org} | {pay} | {sched} | Closes: {close}",
                    "source": "USAJobs"
                })
        return jobs
    except Exception as e:
        print(f"USAJobs failed for '{query}': {e}")
        return []



def gather_all_jobs() -> list[dict]:
    seen = set()
    all_jobs = []
    for query in SEARCH_QUERIES:
        for job in search_adzuna(query):
            if job["url"] not in seen:
                seen.add(job["url"])
                all_jobs.append(job)
    for query in ["production artist", "workflow automation", "creative operations", "implementation analyst", "process automation"]:
        for job in search_usajobs(query):
            if job["url"] not in seen:
                seen.add(job["url"])
                all_jobs.append(job)
        time.sleep(0.3)
    print(f"Found {len(all_jobs)} unique jobs")
    return all_jobs


def score_jobs_with_claude(jobs: list[dict]) -> list[dict]:
    if not jobs:
        return []

    def chunk(lst, n):
        for i in range(0, len(lst), n):
            yield lst[i:i+n]

    all_scored = []
    for batch in chunk(jobs, 25):
        jobs_text = "\n\n".join([
            f"JOB {i+1}:\nTitle: {j['title']}\nCompany: {j.get('company','')}\nLocation: {j.get('location','')}\nURL: {j['url']}\nDescription: {j.get('description','')}"
            for i, j in enumerate(batch)
        ])

        prompt = f"""You are a job search assistant for Sheila Hernandez.

SHEILA'S PROFILE:
{PROFILE}

JOBS TO EVALUATE:
{jobs_text}

Score each job 1-10. Consider: remote or near Bradenton FL, skills match, compensation fit.

Respond ONLY with valid JSON, no markdown:
[{{"job_number":1,"title":"...","company":"...","url":"...","source":"Adzuna","score":8,"reason":"one sentence","flag":"APPLY"}}]

Only include jobs scored 5+. Flag: "APPLY" (8-10), "MAYBE" (5-7). Sort by score descending."""

        try:
            data = json.dumps({
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}]
            }).encode("utf-8")

            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01"
                }
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                result = json.loads(r.read().decode("utf-8"))

            raw = result["content"][0]["text"].strip()
            raw = re.sub(r"^```json\s*|```\s*$", "", raw, flags=re.MULTILINE).strip()
            all_scored.extend(json.loads(raw))
        except Exception as e:
            print(f"Claude scoring failed: {e}")

    all_scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    print(f"Claude scored {len(all_scored)} relevant jobs")
    return all_scored


def build_email_html(scored_jobs: list[dict], total_searched: int) -> str:
    date_str   = datetime.now().strftime("%A, %B %d, %Y")
    apply_jobs = [j for j in scored_jobs if j.get("flag") == "APPLY"]
    maybe_jobs = [j for j in scored_jobs if j.get("flag") == "MAYBE"]

    def job_card(job, color):
        return f"""
        <div style="background:#fff;border-left:4px solid {color};padding:16px 20px;margin-bottom:12px;border-radius:0 4px 4px 0;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;">
            <a href="{job.get('url','#')}" style="font-family:Georgia,serif;font-size:16px;color:#1a1410;text-decoration:none;font-weight:bold;line-height:1.3;flex:1;">{job.get('title','')}</a>
            <span style="background:{color};color:white;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:bold;flex-shrink:0;">{job.get('score','?')}/10</span>
          </div>
          <p style="margin:4px 0 0;font-size:12px;color:#5a4a3a;">{job.get('company','')} · {job.get('location','')}</p>
          <p style="margin:8px 0 0;font-size:13px;color:#8c6a4f;font-style:italic;">{job.get('reason','')}</p>
          <a href="{job.get('url','#')}" style="display:inline-block;margin-top:10px;font-size:12px;color:{color};text-decoration:none;border-bottom:1px solid {color};">View & Apply →</a>
        </div>"""

    apply_html = "".join([job_card(j, "#c4581a") for j in apply_jobs]) if apply_jobs else "<p style='color:#8c6a4f;font-style:italic;'>No strong matches today — check back tomorrow.</p>"
    maybe_html = "".join([job_card(j, "#8c6a4f") for j in maybe_jobs]) if maybe_jobs else ""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f5f0e8;font-family:Arial,sans-serif;">
<div style="max-width:620px;margin:0 auto;padding:24px 16px;">
  <div style="background:#1a1410;padding:28px 32px;">
    <p style="margin:0 0 4px;font-size:11px;letter-spacing:0.2em;text-transform:uppercase;color:#d4b896;">Daily Job Digest</p>
    <h1 style="margin:0;font-family:Georgia,serif;font-size:28px;color:#faf7f2;font-weight:normal;">Good morning, <em style="color:#e8855a;">Sheila</em> ☕</h1>
    <p style="margin:8px 0 0;font-size:13px;color:#8c6a4f;">{date_str} · {total_searched} listings scanned · {len(apply_jobs)} strong matches</p>
  </div>
  <div style="height:4px;background:#c4581a;"></div>
  <div style="background:#faf7f2;padding:28px 32px;">
    {"<h2 style='font-family:Georgia,serif;font-size:18px;color:#c4581a;margin:0 0 16px;font-weight:normal;border-bottom:1px solid #c8b8a2;padding-bottom:8px;'>🎯 Apply Today</h2>" + apply_html if apply_jobs else "<p style='color:#8c6a4f;font-style:italic;padding:16px 0;'>No strong matches today — the agent runs again tomorrow at 7am.</p>"}
    {"<h2 style='font-family:Georgia,serif;font-size:18px;color:#8c6a4f;margin:24px 0 16px;font-weight:normal;border-bottom:1px solid #c8b8a2;padding-bottom:8px;'>🤔 Worth a Look</h2>" + maybe_html if maybe_jobs else ""}
    <div style="margin-top:28px;padding-top:20px;border-top:1px solid #c8b8a2;">
      <p style="font-size:12px;color:#8c6a4f;margin:0;">Your portfolio: <a href="https://shernandez520.github.io" style="color:#c4581a;">shernandez520.github.io</a> · Powered by Claude + GitHub Actions</p>
      <p style="font-size:11px;color:#c8b8a2;margin:6px 0 0;">Nathan approved this digest 🐾</p>
    </div>
  </div>
</div>
</body></html>"""


def send_email(html_body: str, job_count: int):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🎯 {job_count} leads for you today — {datetime.now().strftime('%b %d')}"
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = TO_EMAIL
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, TO_EMAIL, msg.as_string())
    print(f"Email sent to {TO_EMAIL}")


def main():
    print(f"Starting job hunt at {datetime.now()}")
    all_jobs    = gather_all_jobs()
    scored_jobs = score_jobs_with_claude(all_jobs) if all_jobs else []
    apply_count = len([j for j in scored_jobs if j.get("flag") == "APPLY"])
    html        = build_email_html(scored_jobs, len(all_jobs))
    send_email(html, apply_count)
    print("Done!")

if __name__ == "__main__":
    main()
