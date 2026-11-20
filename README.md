# Career Copilot — Agente de Carreira, Vagas Assíncronas e 2º Trabalho

> **Ferramenta universal e plugável de diagnóstico profissional, mineração inteligente de oportunidades remotas (Internacionais USD/EUR e Nacionais PJ) e customização de candidaturas com foco em horários flexíveis e turnos noturnos.**

---

## 🎯 Por que o Career Copilot existe?

A maioria das plataformas de emprego assume que todo profissional busca um trabalho padrão das 9h às 18h com reuniões diárias contínuas. 

O **Career Copilot** foi projetado especificamente para:
1. **Profissionais buscando um 2º trabalho seguro (Moonlighting)**: Analisa entrelinhas de vagas para descartar conflitos de horário com o emprego principal diurno.
2. **Trabalho Noturno e Assíncrono (*Async-First*)**: Prioriza empresas globais que contratam via tickets, PRs, Slack/Notion/Loom e regime *Contractor B2B*.
3. **Compatibilidade Universal com IAs**: Estruturado como um repositório *Agent-First*, pronto para ser operado via **Claude**, **Antigravity**, **Codex**, **Cursor** ou **Terminal CLI**.

---

## 🚀 Como Integrar ao seu Ambiente de IA

### 1. No Claude (Claude Desktop ou Claude Code)
Adicione ao seu `claude_desktop_config.json`:
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

### 2. No Antigravity (Google DeepMind)
O repositório já conta com `AGENTS.md` e servidor MCP nativo. Basta apontar o diretório no seu `mcp_config.json` ou instruir o agente a executar os comandos da CLI.

### 3. No Cursor / Windsurf / Codex
O projeto possui `.cursorrules` e `CLAUDE.md`. Qualquer agente pode ler o perfil, executar a suíte de testes e gerar candidaturas automaticamente.

---

## 💻 Uso via Linha de Comando (CLI)

```powershell
# 1. Diagnóstico do perfil do candidato e viabilidade de horário de trabalho
python -m src.cli profile

# 2. Mineração multicanal (Remotive, Jobicy, We Work Remotely, GitHub BR)
python -m src.cli mine --modo todos --top 10

# 3. Mineração estrita internacional (apenas vagas em USD/EUR)
python -m src.cli mine --modo internacional --min-schedule 60 --top 10

# 4. Geração de Currículo ATS (Google XYZ) e Cold Pitch para a vaga selecionada
python -m src.cli tailor --index 0
```

---

## ⚙️ Configuração do Perfil e Horário Desejado

O arquivo [`configs/perfil.json`](configs/perfil.json) contém as regras de rotina e senioridade:

```json
{
  "horario_trabalho_desejado": {
    "tipo_rotina": "Segundo Trabalho / Turno Noturno & Finais de Semana",
    "timezone_candidato": "America/Sao_Paulo (UTC-3)",
    "janela_disponivel": {
      "segunda_a_sexta": "19:00 - 00:00 (BRT)",
      "finais_de_semana": "Disponível sob demanda para entregas e sprints"
    },
    "turnos_aceitos": ["noturno", "flexivel_assincrono"],
    "carga_semanal_horas": 20,
    "permite_reunioes_horario_comercial": false,
    "politica_comunicacao": "Async-first estrito (sem presença síncrona obrigatória entre 09h e 18h BRT)"
  }
}
```

---

## 📂 Arquitetura do Repositório

```text
career-copilot/
├── configs/
│   ├── perfil_template.json      # Template base para novos candidatos
│   └── perfil.json               # Configurações ativas do usuário
├── src/
│   ├── profiler/                 # Diagnóstico de senioridade e skill gaps
│   ├── evaluators/               # Cruzamento de fuso horário e rotina (schedule matcher)
│   ├── miners/                   # Coletores de APIs públicas (Remotive, Jobicy, WWR, GitHub BR)
│   ├── tailor/                   # Reescrita Google XYZ e gerador de cold pitch
│   ├── cli.py                    # Interface de linha de comando
│   └── mcp_server.py             # Servidor MCP stdio universal
├── data/
│   └── vagas_mineradas.json      # Base de dados local com histórico
├── tests/                        # Suíte de testes automatizados com pytest
├── AGENTS.md                     # Manual operacional para Antigravity e Codex
├── CLAUDE.md                     # Manual operacional para Claude
├── .cursorrules                  # Regras para Cursor e Windsurf
└── pyproject.toml
```

---

## 🧪 Testes Automatizados

```bash
pytest
```
*Totalmente coberto com testes de unidade para validação de compatibilidade horária e perfil.*
