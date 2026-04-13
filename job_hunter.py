"""
Sheila's Automated Job Hunter
Searches for contract opportunities daily and emails a curated digest.
"""

import os
import re
import json
import smtplib
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── CONFIG ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GMAIL_ADDRESS     = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
TO_EMAIL          = "shernandez520@gmail.com"

# Job search queries — casting wide, Claude will score/filter
SEARCH_QUERIES = [
    "production artist remote contract",
    "creative operations specialist remote",
    "workflow automation specialist remote contract",
    "implementation analyst remote contract",
    "print production artist contract",
    "creative ops manager remote",
    "promotional products artwork remote",
    "process automation specialist contract remote",
    "art director production remote contract",
]

# Sheila's profile for Claude scoring
PROFILE = """
Sheila Hernandez — Contract Candidate Profile:
- 20+ years in promotional products industry (supplier AND distributor side)
- Production artist: vector cleanup, file prep, color separations, screen print/embroidery/sublimation/laser setup
- Workflow automation: Python, PowerShell, Make.com, Zapier, Adobe ExtendScript
- Implementation analyst: process design, systems implementation, cross-functional stakeholder management
- Built ArtCheck (artcheck.app) — live SaaS art file screening tool with organic traction
- Built FINALIZER — internal batch automation suite at national distributor
- Tools: Adobe Illustrator, Photoshop, InDesign, CorelDRAW, NetSuite, Streamlit, GitHub
- 5/5 performance review (Exceptional), April 2026
- Looking for: part-time remote contract work, $55/hr, open to within 20 miles of Bradenton FL (34209) or fully remote
- Available immediately
"""

# ── INDEED RSS SEARCH ─────────────────────────────────────────────────────────
def search_indeed_rss(query: str, location: str = "remote") -> list[dict]:
    """Fetch jobs from Indeed RSS feed."""
    encoded_query = urllib.parse.quote(query)
    encoded_location = urllib.parse.quote(location)
    url = f"https://www.indeed.com/rss?q={encoded_query}&l={encoded_location}&jt=contract&radius=20&sort=date"
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode("utf-8")
        
        root = ET.fromstring(content)
        jobs = []
        for item in root.findall(".//item")[:5]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            description = item.findtext("description", "")
            pub_date = item.findtext("pubDate", "")
            # Clean HTML from description
            clean_desc = re.sub(r"<[^>]+>", " ", description).strip()
            clean_desc = re.sub(r"\s+", " ", clean_desc)[:400]
            
            if title and link:
                jobs.append({
                    "title": title,
                    "link": link,
                    "description": clean_desc,
                    "date": pub_date,
                    "source": "Indeed"
                })
        return jobs
    except Exception as e:
        print(f"RSS fetch failed for '{query}': {e}")
        return []


def gather_all_jobs() -> list[dict]:
    """Run all search queries and deduplicate by URL."""
    seen_links = set()
    all_jobs = []
    
    for query in SEARCH_QUERIES:
        jobs = search_indeed_rss(query)
        for job in jobs:
            if job["link"] not in seen_links:
                seen_links.add(job["link"])
                all_jobs.append(job)
        
        # Also search near Bradenton
        jobs_local = search_indeed_rss(query, "Bradenton, FL")
        for job in jobs_local:
            if job["link"] not in seen_links:
                seen_links.add(job["link"])
                all_jobs.append(job)
    
    print(f"Found {len(all_jobs)} unique jobs before scoring")
    return all_jobs


# ── CLAUDE SCORING ────────────────────────────────────────────────────────────
def score_jobs_with_claude(jobs: list[dict]) -> list[dict]:
    """Send jobs to Claude for scoring against Sheila's profile."""
    if not jobs:
        return []
    
    jobs_text = "\n\n".join([
        f"JOB {i+1}:\nTitle: {j['title']}\nURL: {j['link']}\nDescription: {j['description']}"
        for i, j in enumerate(jobs)
    ])
    
    prompt = f"""You are a job search assistant for Sheila Hernandez.

SHEILA'S PROFILE:
{PROFILE}

JOBS TO EVALUATE:
{jobs_text}

Score each job 1-10 for fit. Consider:
- Remote or within 20 miles of Bradenton FL (34209)
- Contract/freelance work (not full-time permanent)
- Matches her skills: production art, workflow automation, creative ops, implementation
- Reasonable for $45-65/hr contract rate
- Part-time friendly is a bonus

Respond ONLY with valid JSON, no markdown, no explanation:
[
  {{
    "job_number": 1,
    "title": "...",
    "url": "...",
    "score": 8,
    "reason": "One sentence why this fits or doesn't",
    "flag": "APPLY" or "MAYBE" or "SKIP"
  }},
  ...
]

Only include jobs scored 5 or above. Sort by score descending."""

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
        
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
        
        raw = result["content"][0]["text"].strip()
        # Strip markdown fences if present
        raw = re.sub(r"^```json\s*|```\s*$", "", raw, flags=re.MULTILINE).strip()
        scored = json.loads(raw)
        print(f"Claude scored {len(scored)} relevant jobs")
        return scored
    
    except Exception as e:
        print(f"Claude scoring failed: {e}")
        return []


# ── EMAIL DIGEST ──────────────────────────────────────────────────────────────
def build_email_html(scored_jobs: list[dict], total_searched: int) -> str:
    """Build a beautiful HTML email digest."""
    date_str = datetime.now().strftime("%A, %B %d, %Y")
    
    apply_jobs = [j for j in scored_jobs if j.get("flag") == "APPLY"]
    maybe_jobs = [j for j in scored_jobs if j.get("flag") == "MAYBE"]
    
    def job_card(job, color):
        score = job.get("score", "?")
        return f"""
        <div style="background:#fff; border-left:4px solid {color}; padding:16px 20px; margin-bottom:12px; border-radius:0 4px 4px 0; box-shadow:0 1px 3px rgba(0,0,0,0.08);">
            <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                <a href="{job.get('url','#')}" style="font-family:Georgia,serif; font-size:17px; color:#1a1410; text-decoration:none; font-weight:bold; line-height:1.3;">{job.get('title','Untitled')}</a>
                <span style="background:{color}; color:white; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:bold; margin-left:12px; white-space:nowrap;">{score}/10</span>
            </div>
            <p style="margin:8px 0 0; font-size:13px; color:#8c6a4f; font-style:italic;">{job.get('reason','')}</p>
            <a href="{job.get('url','#')}" style="display:inline-block; margin-top:10px; font-size:12px; color:{color}; text-decoration:none; border-bottom:1px solid {color};">View & Apply →</a>
        </div>"""
    
    apply_html = "".join([job_card(j, "#c4581a") for j in apply_jobs]) if apply_jobs else "<p style='color:#8c6a4f; font-style:italic;'>No strong matches today — check back tomorrow.</p>"
    maybe_html = "".join([job_card(j, "#8c6a4f") for j in maybe_jobs]) if maybe_jobs else ""
    
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0; padding:0; background:#f5f0e8; font-family:Arial,sans-serif;">
  <div style="max-width:600px; margin:0 auto; padding:24px 16px;">
    
    <!-- HEADER -->
    <div style="background:#1a1410; padding:28px 32px; margin-bottom:0;">
      <p style="margin:0 0 4px; font-size:11px; letter-spacing:0.2em; text-transform:uppercase; color:#d4b896;">Daily Job Digest</p>
      <h1 style="margin:0; font-family:Georgia,serif; font-size:28px; color:#faf7f2; font-weight:normal;">Good morning, <em style="color:#e8855a;">Sheila</em> ☕</h1>
      <p style="margin:8px 0 0; font-size:13px; color:#8c6a4f;">{date_str} · {total_searched} listings scanned · {len(apply_jobs)} strong matches</p>
    </div>
    
    <!-- RUST BAR -->
    <div style="height:4px; background:#c4581a;"></div>
    
    <!-- BODY -->
    <div style="background:#faf7f2; padding:28px 32px;">
      
      {"<h2 style='font-family:Georgia,serif; font-size:18px; color:#c4581a; margin:0 0 16px; font-weight:normal; border-bottom:1px solid #c8b8a2; padding-bottom:8px;'>🎯 Apply Today</h2>" + apply_html if apply_jobs else ""}
      
      {"<h2 style='font-family:Georgia,serif; font-size:18px; color:#8c6a4f; margin:24px 0 16px; font-weight:normal; border-bottom:1px solid #c8b8a2; padding-bottom:8px;'>🤔 Worth a Look</h2>" + maybe_html if maybe_jobs else ""}
      
      <!-- FOOTER NOTE -->
      <div style="margin-top:28px; padding-top:20px; border-top:1px solid #c8b8a2;">
        <p style="font-size:12px; color:#8c6a4f; margin:0;">Your portfolio: <a href="https://shernandez520.github.io" style="color:#c4581a;">shernandez520.github.io</a> · Powered by Claude + GitHub Actions</p>
        <p style="font-size:11px; color:#c8b8a2; margin:6px 0 0;">Nathan approved this digest 🐾</p>
      </div>
    </div>
    
  </div>
</body>
</html>"""


def send_email(html_body: str, job_count: int):
    """Send the digest via Gmail SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🎯 {job_count} contract leads for you today — {datetime.now().strftime('%b %d')}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = TO_EMAIL
    msg.attach(MIMEText(html_body, "html"))
    
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, TO_EMAIL, msg.as_string())
    
    print(f"Email sent to {TO_EMAIL}")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print(f"Starting job hunt at {datetime.now()}")
    
    # 1. Gather jobs
    all_jobs = gather_all_jobs()
    
    if not all_jobs:
        print("No jobs found today. Sending empty digest.")
        html = build_email_html([], 0)
        send_email(html, 0)
        return
    
    # 2. Score with Claude
    scored_jobs = score_jobs_with_claude(all_jobs)
    
    # 3. Build and send email
    apply_count = len([j for j in scored_jobs if j.get("flag") == "APPLY"])
    html = build_email_html(scored_jobs, len(all_jobs))
    send_email(html, apply_count)
    
    print("Done!")


if __name__ == "__main__":
    main()
