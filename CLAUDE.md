# CLAUDE.md — Career Copilot Guide

This repository contains **Career Copilot**, an agent-first career diagnostic and job search automation tool focused on flexible, night-shift, and async-first remote roles (International USD/EUR & National PJ).

## Core Capabilities
1. **Career & Profile Analysis**: Evaluates developer seniorities, tech stack, and compatibility with target working hours (night shift 19:00 - 00:00 BRT).
2. **Schedule Conflict Matcher**: Flags overlapping mandatory meetings, strict 9-5 core hours, and identifies async-friendly opportunities.
3. **Multichannel Job Miner**: Real-time integration with Remotive, Jobicy, WeWorkRemotely, and GitHub Brazil remote job boards.
4. **ATS Tailoring Engine**: Dynamically rewrites resumes in Markdown and generates tailored cold outreach pitches in both English and Portuguese.

## Common Commands
```bash
# Run test suite
pytest

# View career diagnosis and working hours fit
python -m src.cli profile

# Mine qualified opportunities
python -m src.cli mine --modo todos --top 10

# Generate tailored CV and cover pitch for the top vacancy
python -m src.cli tailor --index 0

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
      "cwd": "D:\\Desktop\\Códigos\\career-copilot"
    }
  }
}
```
