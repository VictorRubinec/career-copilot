# CLAUDE.md — Career Copilot Guide

This repository contains **Career Copilot**, an agent-first career diagnostic and job search automation tool focused on flexible, night-shift, and async-first remote roles (International USD/EUR & National PJ).

## Core Capabilities
1. **Career & Profile Analysis**: Evaluates developer seniorities, tech stack, and compatibility with target working hours (night shift 19:00 - 00:00 BRT) using strict Pydantic v2 models (`src/models.py`).
2. **Schedule Conflict Matcher**: Context-aware regex matcher that blocks onsite/relocation roles and mandatory daytime standups/core hours while rewarding genuine async-first and contractor B2B signals.
3. **Multichannel Resilient Job Miner**: Concurrent mining across Remotive, Jobicy, WeWorkRemotely, GitHub Brazil, public ATS boards (Greenhouse, Ashby, Lever via `configs/ats_boards.json`), and Hacker News "Who is Hiring" (Algolia API), backed by exponential backoff, per-domain rate limiting, and TTL disk cache (`src/miners/http_client.py`).
4. **ATS Tailoring Engine**: Dynamically rewrites resumes in Markdown from the candidate profile and generates tailored cold outreach pitches in both English and Portuguese.
5. **7 Personas Hiring Board (`src/evaluators/committee.py`)**: Multi-perspective application audit (ATS Screener, Tech Recruiter, Engineering Manager, Senior Peer Developer, Product Manager, CTO / Head, Recrutador Cético) with Structured Outputs, consensus rule (mean >= 8.0/10), and automatic veto when ATS or Recrutador Cético scores < 7.0.
6. **Corporate A4 PDF Compiler (`src/tailor/pdf_compiler.py`)**: Compiles Markdown resumes into tagged, ATS-parseable corporate A4 PDFs via Playwright Chromium headless (`Inter` / `JetBrains Mono` typography, anti-orphan pagination rules, and corporate PDF metadata via `pypdf`).
7. **Human-in-the-Loop Copilot (`src/copiloto/`)**: Pre-authenticated persistent Playwright assistant that checks schedule compatibility, auto-fills form fields and screening answers, uploads the compiled A4 PDF, pauses on CAPTCHAs/login walls, and never auto-submits without human review (`submetido_automaticamente: false`).

## Common Commands
```bash
# Run test suite
pytest

# View career diagnosis and working hours fit
python -m src.cli profile

# Mine qualified opportunities (all sources)
python -m src.cli mine --modo todos --top 10

# Mine specific ATS / Hacker News sources bypassing HTTP cache
python -m src.cli mine --fontes greenhouse,ashby,lever,hackernews --no-cache --top 10

# Generate tailored CV, cover pitch (+ 7-persona review & A4 PDF) for the top vacancy
python -m src.cli tailor --index 0 --with-review --pdf

# Run the 7 Personas Hiring Board review independently
python -m src.cli review --index 0

# Export corporate A4 PDF directly
python -m src.cli pdf --index 0

# Prepare and autofill an application in Human-in-the-Loop mode (or --dry-run)
python -m src.cli apply --index 0

# Start MCP stdio server
python -m src.mcp_server
```

## MCP Integration Configuration
To connect this tool to Claude Desktop or Claude Code, add this entry to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "career-copilot": {
      "command": "python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "/path/to/career-copilot"
    }
  }
}
```
