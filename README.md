# Career Copilot — Agente Autônomo de Carreira, Vagas Assíncronas & Moonlighting

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![MCP Ready](https://img.shields.io/badge/Protocolo-MCP%20stdio-0F172A)](https://modelcontextprotocol.io/)
[![Playwright](https://img.shields.io/badge/Automação-Playwright%20Chromium-2EAD33?logo=playwright&logoColor=white)](https://playwright.dev/python/)

> **Suíte *Agent-First* de diagnóstico profissional, mineração resiliente multicanal, auditoria cognitiva por comitê de contratação, compilação de PDF A4 corporativo e copiloto de candidatura *Human-in-the-Loop* — projetada para rotinas noturnas, turnos flexíveis e trabalho 100% assíncrono.**

---

## Por que o Career Copilot existe?

A maioria das plataformas de emprego presume que todo profissional busca trabalho presencial ou síncrono das 9h às 18h. O **Career Copilot** resolve exatamente essa lacuna:

- **Segundo Trabalho Seguro (Moonlighting)**: Analisa entrelinhas das vagas com regex contextuais para bloquear colisões com o horário comercial diurno (`09:00–18:00 BRT`), evitando falsos positivos técnicos (`asynchronous processing`, `B2B SaaS`, licença parental).
- **Turno Noturno & Cultura *Async-First***: Prioriza posições guiadas por tickets, PRs, Slack/Notion/Loom, contratos **Contractor B2B (USD/EUR)** e **PJ Flexível (BRL)**.
- **Interoperabilidade Universal**: Operável como **Servidor MCP (`stdio`)** para Claude, Antigravity, Cursor e Codex, via **CLI** (`python -m src.cli`), menu Windows (`run.bat`) ou como biblioteca Python importável.

---

## Arquitetura & Capacidades (5 Camadas)

1. **Core Estritamente Tipado & Filtro Anti-Conflito** ([`src/models.py`](src/models.py), [`src/config.py`](src/config.py), [`src/evaluators/schedule_matcher.py`](src/evaluators/schedule_matcher.py))
   - Schemas Pydantic v2 para perfil, vagas, diagnósticos e sessões; persistência JSON/binária atômica (`os.replace`); logging restrito a `stderr` (preservando o canal `stdio` do MCP).
   - Classificação explícita `[COMPATÍVEL]` / `[PARCIALMENTE COMPATÍVEL]` / `[INCOMPATÍVEL]` com veto absoluto para presença obrigatória, realocação, câmeras abertas e dailies em horário comercial.

2. **Minerador Multicanal Resiliente** ([`src/miners/`](src/miners/))
   - **8 fontes concorrentes** via `ThreadPoolExecutor` com isolamento de falhas e deduplicação determinística:
     - **Boards Remotos & Comunidade**: Remotive, Jobicy, WeWorkRemotely (RSS) e GitHub Brasil (`backend-br/vagas`, `qa-brasil/vagas`).
     - **ATS Corporativos Públicos**: Greenhouse, Ashby e Lever configuráveis em [`configs/ats_boards.json`](configs/ats_boards.json).
     - **Hacker News `"Who is Hiring?"`**: Coleta mensal via Algolia API filtrando comentários top-level por `remote`, `async`, `contractor` e `python`.
   - **Camada HTTP Resiliente** ([`http_client.py`](src/miners/http_client.py)): *exponential backoff* com jitter, respeito a `429 Retry-After`, rate-limiting thread-safe por domínio e cache local em disco com TTL.

3. **Banca Examinadora Cognitiva — The 7 Personas Hiring Board** ([`src/evaluators/committee.py`](src/evaluators/committee.py))
   - Auditoria multidimensional com Structured Outputs avaliando:
     1. **ATS Screener** (keywords & parseabilidade)
     2. **Tech Recruiter** (regra dos 6 segundos & senioridade)
     3. **Engineering Manager** (arquitetura, concorrência & profundidade)
     4. **Senior Peer Developer** (qualidade de código, testes & CI/CD)
     5. **Product Manager** (métricas Google XYZ & impacto)
     6. **CTO / Head** (governança, observabilidade & maturidade assíncrona)
     7. **Recrutador Cético** (caçador de clichês, placeholders & conflitos de rotina)
   - **Regra de Consenso**: Aprovação exige `media_geral >= 8.0/10` e aplica **veto automático (`VETADO`)** caso `ATS Screener < 7.0` ou `Recrutador Cético < 7.0`. Suporta modo determinístico offline e provedor plugável Gemini (`create_gemini_committee_provider`).

4. **Motor de Compilação de PDF A4 Corporativo** ([`src/tailor/pdf_compiler.py`](src/tailor/pdf_compiler.py))
   - Compila o currículo calibrado em Markdown para **PDF A4 corporativo** via **Playwright Chromium headless** (`tagged=True`, `outline=True`).
   - Fluxo semântico de coluna única 100% legível por ATS, tipografia `Inter` & `JetBrains Mono`, regras CSS anti-órfãos (`break-inside: avoid`, `orphans/widows: 3`) e metadados corporativos embutidos e auditados via `pypdf` (`inspect_pdf_ats_readability`).

5. **Copiloto Human-in-the-Loop** ([`src/copiloto/`](src/copiloto/))
   - Verifica conflito de rotina antes de abrir o navegador e registra sessões idempotentes em `data/candidaturas_log.json`.
   - Utiliza perfil persistente pré-autenticado (`data/browser_profile/`), preenche campos pessoais/links, anexa o PDF A4 compilado, responde perguntas de triagem assíncrona e **pausa com banner de revisão humana** (detecção passiva de CAPTCHAs e paredes de login, sem qualquer tentativa de bypass).

---

## Instalação & Início Rápido

### 1. Clonar e instalar dependências
```bash
git clone https://github.com/VictorRubinec/career-copilot.git
cd career-copilot

python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux/macOS:
# source .venv/bin/activate

pip install -e ".[dev]"
playwright install chromium
```

### 2. Configurar seu perfil (privado e ignorado no Git)
```powershell
Copy-Item configs/perfil_template.json configs/perfil.json
# Opcional: copie .env.example para .env para tokens opcionais (GITHUB_TOKEN / GEMINI_API_KEY)
Copy-Item .env.example .env
```
Edite [`configs/perfil.json`](configs/perfil.json) com seus dados reais, janela horária noturna (`19:00 - 00:00 BRT`), competências e histórico no padrão Google XYZ (com métricas numéricas).

---

## Guia Completo da CLI

Você pode usar `python -m src.cli ...` (ou o menu interativo [`run.bat`](run.bat) no Windows):

```powershell
# 1. Diagnóstico de perfil, senioridade e viabilidade da rotina noturna
python -m src.cli profile

# 2. Mineração concorrente em todas as 8 fontes (com cache HTTP TTL)
python -m src.cli mine --modo todos --top 10

# 3. Mineração direcionada a ATS corporativos e Hacker News sem cache
python -m src.cli mine --fontes greenhouse,ashby,lever,hackernews --no-cache --top 10

# 4. Mineração estritamente internacional (USD/EUR)
python -m src.cli mine --modo internacional --min-schedule 60 --top 10

# 5. Calibrar currículo ATS, gerar Cold Pitch (EN/PT), auditar na Banca e compilar PDF A4
python -m src.cli tailor --index 0 --with-review --pdf

# 6. Rodar a Banca Examinadora Cognitiva (7 Personas) isoladamente (aceita --resume custom.md)
python -m src.cli review --index 0

# 7. Compilar currículo para PDF A4 Corporativo diretamente (salva em data/curriculos_gerados/)
python -m src.cli pdf --index 0

# 8. Copiloto Human-in-the-Loop: prepara PDF, abre navegador, preenche campos e pausa
python -m src.cli apply --index 0 --dry-run
python -m src.cli apply --index 0
```

---

## Integração Universal com Agentes de IA (MCP)

O servidor [`src/mcp_server.py`](src/mcp_server.py) expõe 7 ferramentas nativas via transporte `stdio`:

| Ferramenta MCP | Finalidade |
|---|---|
| `get_career_profile` | Diagnóstico de senioridade, prontidão internacional e viabilidade de turno |
| `mine_jobs` | Mineração concorrente filtrada por rotina, stack, fontes e cache TTL |
| `evaluate_job` | Análise de conflitos de horário e gaps técnicos para uma vaga avulsa |
| `tailor_application` | Geração de currículo ATS em Markdown + Cold Pitch (EN e PT) |
| `review_application` | Auditoria multidimensional pela Banca das 7 Personas (consenso & veto) |
| `export_resume_pdf` | Compilação de currículo para PDF A4 corporativo via Chromium headless |
| `assist_application` | Copiloto Human-in-the-Loop via Playwright (pausa obrigatória antes do envio) |

### Configuração em Clientes MCP (Claude Desktop, Claude Code, Antigravity, Cursor)

Ajuste `cwd` no arquivo [`mcp_config.json`](mcp_config.json) ou adicione ao `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "career-copilot": {
      "command": "python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "/caminho/para/career-copilot"
    }
  }
}
```

O repositório inclui ainda guias dedicados para agentes em [`AGENTS.md`](AGENTS.md), [`CLAUDE.md`](CLAUDE.md) e [`.cursorrules`](.cursorrules).

---

## Segurança, Privacidade & Human-in-the-Loop

- **Zero Auto-Submissão**: O esquema `CopilotSessionResult` impõe `submetido_automaticamente: Literal[False] = False`. O copiloto nunca clica em botões de envio/submissão sem confirmação humana explícita.
- **Respeito a Gates Externos**: Ao detectar CAPTCHAs (`reCAPTCHA`, `hCaptcha`, `Cloudflare Turnstile`) ou telas de login, o assistente pausa imediatamente e delega a ação ao usuário no navegador persistente.
- **Privacidade Local por Padrão**: Dados pessoais e sessões locais (`configs/perfil.json`, `.env`, `data/vagas_mineradas.json`, `data/curriculos_gerados/`, `data/http_cache/`, `data/browser_profile/`, `data/candidaturas_log.json`) permanecem fora do Git via [`.gitignore`](.gitignore).

---

## Estrutura do Repositório

```text
career-copilot/
├── configs/
│   ├── ats_boards.json           # Boards públicos configuráveis (Greenhouse, Ashby, Lever)
│   └── perfil_template.json      # Template limpo para novos candidatos
├── src/
│   ├── models.py                 # Schemas Pydantic v2 (perfil, vagas, banca, PDF, copiloto)
│   ├── config.py                 # Caminhos, overrides via env, logging stderr e escrita atômica
│   ├── profiler/                 # Diagnóstico de senioridade e skill gaps
│   ├── evaluators/               # schedule_matcher.py e Banca das 7 Personas (committee.py)
│   ├── miners/                   # http_client.py + coletores (Remotive, Jobicy, WWR, GitHub BR, ATS, HN)
│   ├── tailor/                   # Calibrador ATS, cold pitch e compilador PDF A4 (pdf_compiler.py)
│   ├── copiloto/                 # Copiloto Human-in-the-Loop via Playwright (assistant.py, form_mapper.py)
│   ├── cli.py                    # Interface de linha de comando
│   └── mcp_server.py             # Servidor MCP stdio universal
├── tests/                        # Suíte de testes offline com pytest e mocks HTTP/DOM
├── .env.example                  # Exemplo de variáveis de ambiente opcionais
├── mcp_config.json               # Configuração modelo para clientes MCP
├── AGENTS.md / CLAUDE.md         # Guias operacionais para agentes de IA
├── .cursorrules                  # Regras contextuais para editores
├── pyproject.toml                # Empacotamento e configuração pytest
└── run.bat                       # Menu operacional rápido no Windows
```

---

## Testes Automatizados

Toda a suíte roda offline (requisições HTTP mockadas via `httpx.MockTransport` e formulários locais `file://` para testes reais do Playwright Chromium) sem tocar nos seus dados pessoais:

```bash
pytest -v -W error --cov=src --cov-report=term-missing
```
