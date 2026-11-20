def generate_cover_pitch(profile_data, job_data):
    """
    Gera mensagens de abordagem (Cold Pitch e Cover Letter) em Inglês e Português.
    """
    candidato = profile_data.get("candidato", {})
    titulo_vaga = job_data.get("titulo", "Software Engineer")
    empresa = job_data.get("empresa", "Hiring Team")

    pitch_ingles = f"""Subject: Application: {titulo_vaga} — {candidato.get('nome')}

Hi {empresa} Team,

I came across your opening for {titulo_vaga} and wanted to reach out directly. 

With a strong foundation in Python automation, backend APIs, and data workflows (ETL/SQL), I have built reliable web test suites, automated health checks, and data pipelines that streamlined production operations at TIVIT. 

I thrive in autonomous, async-first environments where execution is driven by tickets, PRs, and clear documentation. Given your distributed team setup, my working style and availability align seamlessly with your engineering cadence.

I would love to learn more about the challenges your team is currently tackling. My resume is attached, and you can also explore my background on LinkedIn ({candidato.get('contato', {}).get('linkedin')}).

Best regards,
{candidato.get('nome')}
{candidato.get('contato', {}).get('email')}
"""

    pitch_portugues = f"""Assunto: Candidatura: {titulo_vaga} — {candidato.get('nome')}

Olá, equipe da {empresa},

Gostaria de apresentar minha candidatura para a posição de {titulo_vaga}.

Tenho sólida experiência em automação de processos, desenvolvimento Python, consultas SQL e rotinas de ETL construídas em ambientes corporativos de missão crítica (TIVIT). Minha atuação sempre foi focada em eliminar gargalos manuais, garantir alta cobertura de testes e integrar serviços via APIs REST resilientes.

Opero com alta autonomia e comunicação assíncrona clara (Slack, Notion, PRs no GitHub), sendo um encaixe ideal para equipes dinâmicas orientadas a entregas.

Fico à total disposição para um breve bate-papo técnico.

Atenciosamente,
{candidato.get('nome')}
{candidato.get('contato', {}).get('telefone')} | {candidato.get('contato', {}).get('email')}
"""

    return {
        "vaga": f"{titulo_vaga} @ {empresa}",
        "pitch_ingles": pitch_ingles.strip(),
        "pitch_portugues": pitch_portugues.strip()
    }
