"""Modelos de domínio tipados com Pydantic v2 para o Career Copilot."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ScheduleStatus = Literal["COMPATIVEL", "PARCIALMENTE_COMPATIVEL", "INCOMPATIVEL"]

SCHEDULE_STATUS_LABELS: dict[ScheduleStatus, str] = {
    "COMPATIVEL": "[COMPATÍVEL]",
    "PARCIALMENTE_COMPATIVEL": "[PARCIALMENTE COMPATÍVEL]",
    "INCOMPATIVEL": "[INCOMPATÍVEL]",
}


class ContactInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str = ""
    telefone: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""


class CandidateInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nome: str = "Candidato"
    titulo_principal: str = ""
    localizacao: str = ""
    contato: ContactInfo = Field(default_factory=ContactInfo)


class MinCompensation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    usd_hora: float = 0.0
    usd_mensal: float = 0.0
    brl_hora: float = 0.0
    brl_mensal: float = 0.0


class CareerPreferences(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cargos_alvo: list[str] = Field(default_factory=list)
    senioridade_alvo: list[str] = Field(default_factory=list)
    modalidades: list[str] = Field(default_factory=list)
    regimes_contratuais: list[str] = Field(default_factory=list)
    remuneracao_minima: MinCompensation = Field(default_factory=MinCompensation)


class DesiredSchedule(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tipo_rotina: str = "Segundo Trabalho / Turno Noturno"
    timezone_candidato: str = "America/Sao_Paulo (UTC-3)"
    janela_disponivel: dict[str, str] = Field(default_factory=dict)
    turnos_aceitos: list[str] = Field(
        default_factory=lambda: ["noturno", "flexivel_assincrono"]
    )
    carga_semanal_horas: int = 20
    permite_reunioes_horario_comercial: bool = False
    maximo_horas_sincronas_semana: int = 2
    politica_comunicacao: str = ""


class Competencies(BaseModel):
    model_config = ConfigDict(extra="ignore")

    principais: list[str] = Field(default_factory=list)
    secundarias: list[str] = Field(default_factory=list)
    idiomas: dict[str, str] = Field(default_factory=dict)


class ExperienceEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    empresa: str
    cargo: str
    periodo: str = ""
    atividades: list[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    titulo: str
    detalhe: str = ""

    @model_validator(mode="before")
    @classmethod
    def _coerce_string(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"titulo": value, "detalhe": ""}
        return value


class CandidateProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidato: CandidateInfo = Field(default_factory=CandidateInfo)
    preferencias_carreira: CareerPreferences = Field(default_factory=CareerPreferences)
    horario_trabalho_desejado: DesiredSchedule = Field(default_factory=DesiredSchedule)
    competencias: Competencies = Field(default_factory=Competencies)
    historico_profissional: list[ExperienceEntry] = Field(default_factory=list)
    formacao_e_certificacoes: list[EducationEntry] = Field(default_factory=list)


class ScheduleFitResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    score_horario: int = Field(ge=0, le=100)
    status: ScheduleStatus
    classificacao_exibicao: str
    justificativa: str
    red_flags: list[str] = Field(default_factory=list)
    sinais_positivos: list[str] = Field(default_factory=list)
    janela_candidato: dict[str, str] = Field(default_factory=dict)
    permite_reunioes_comercial: bool = False


class RawJobOpportunity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    fonte: str
    origem: str
    empresa: str
    titulo: str
    localizacao: str
    tipo_contrato: str
    salario: str
    url: str
    data_publicacao: str = ""
    descricao: str = ""
    resumo: str = ""


class QualifiedJobOpportunity(RawJobOpportunity):
    schedule_fit: ScheduleFitResult
    stack_score: int = Field(ge=0, le=100)
    matches_stack: list[str] = Field(default_factory=list)
    score_composto: float = Field(ge=0.0, le=100.0)


class MiningSourceStats(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fonte: str
    coletadas: int = 0
    erro: str | None = None


class CandidateSummary(BaseModel):
    nome: str
    titulo: str
    localizacao: str


class CareerDiagnosticDetails(BaseModel):
    senioridade_estimada: str
    senioridade_alvo: list[str] = Field(default_factory=list)
    cargos_alvo: list[str] = Field(default_factory=list)
    nivel_autonomia: str
    readiness_internacional_score: int = Field(ge=0, le=100)


class ScheduleViability(BaseModel):
    status: str
    janela_declarada: str
    carga_alvo: str
    regime_recomendado: str
    pontos_atencao: str


class CareerDiagnosis(BaseModel):
    candidato: CandidateSummary
    diagnostico_carreira: CareerDiagnosticDetails
    analise_horario_trabalho: ScheduleViability
    competencias_chave: Competencies
    proximos_passos_recomendados: list[str] = Field(default_factory=list)


class JobSummary(BaseModel):
    titulo: str
    empresa: str
    origem: str


class TechnicalFitSummary(BaseModel):
    match_pct: float = Field(ge=0.0, le=100.0)
    skills_atendidas: list[str] = Field(default_factory=list)
    gaps_identificados: list[str] = Field(default_factory=list)


class JobGapReport(BaseModel):
    vaga: JobSummary
    score_geral: float = Field(ge=0.0, le=100.0)
    compatibilidade_horario: ScheduleFitResult
    aderencia_tecnica: TechnicalFitSummary
    recomendacao_acao: str


class TailoredResume(BaseModel):
    vaga_alvo: str
    curriculo_markdown: str


class CoverPitchBundle(BaseModel):
    vaga: str
    pitch_ingles: str
    pitch_portugues: str


PersonaId = Literal[
    "ats_screener",
    "tech_recruiter",
    "engineering_manager",
    "senior_peer",
    "product_manager",
    "cto_head",
    "skeptic_recruiter",
]

CommitteeVerdict = Literal["APROVADO", "VETADO", "REVISAR"]
EvaluationMode = Literal["heuristico_deterministico", "llm_estruturado"]

ALL_PERSONA_IDS: tuple[PersonaId, ...] = (
    "ats_screener",
    "tech_recruiter",
    "engineering_manager",
    "senior_peer",
    "product_manager",
    "cto_head",
    "skeptic_recruiter",
)


class PersonaEvaluation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    persona_id: PersonaId
    persona_nome: str
    nota: float = Field(ge=0.0, le=10.0)
    foco_avaliacao: str
    pontos_fortes: list[str] = Field(default_factory=list)
    lacunas_e_riscos: list[str] = Field(default_factory=list)
    acoes_corretivas: list[str] = Field(default_factory=list)
    justificativa: str


class CommitteePersonaBatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    avaliacoes: list[PersonaEvaluation]

    @field_validator("avaliacoes")
    @classmethod
    def _validate_all_seven_personas(
        cls, value: list[PersonaEvaluation]
    ) -> list[PersonaEvaluation]:
        ids = [item.persona_id for item in value]
        if len(value) != len(ALL_PERSONA_IDS) or set(ids) != set(ALL_PERSONA_IDS):
            raise ValueError(
                "A banca examinadora exige exatamente 1 avaliação para cada uma das 7 personas distintas."
            )
        return value


class CommitteeVetoDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ativo: bool = False
    personas_vetadoras: list[PersonaId] = Field(default_factory=list)
    motivos: list[str] = Field(default_factory=list)


class CommitteeEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vaga_alvo: str
    veredito: CommitteeVerdict
    aprovado: bool
    media_geral: float = Field(ge=0.0, le=10.0)
    limiar_aprovacao: float = 8.0
    limiar_veto_critico: float = 7.0
    veto: CommitteeVetoDetail
    avaliacoes: list[PersonaEvaluation]
    compatibilidade_horario: ScheduleFitResult
    plano_acao_prioritario: list[str] = Field(default_factory=list)
    modo_avaliacao: EvaluationMode = "heuristico_deterministico"
    resumo_executivo: str


class PDFMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    author: str
    subject: str = "Currículo Profissional — Career Copilot"
    keywords: list[str] = Field(default_factory=list)
    creator: str = "Career Copilot PDF Engine (Playwright Chromium)"


class CompiledPDFResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vaga_alvo: str
    pdf_path: str
    html_path: str | None = None
    tamanho_bytes: int = Field(ge=0)
    paginas: int = Field(ge=1)
    ats_legivel: bool = True
    metadados: PDFMetadata
    sha256: str


ApplicationFormFieldType = Literal[
    "text", "email", "tel", "url", "textarea", "file", "select"
]

CopilotSessionStatus = Literal[
    "AGUARDANDO_REVISAO_HUMANA",
    "PAUSADO_VERIFICACAO_HUMANA",
    "BLOQUEADO_CONFLITO_HORARIO",
    "DRY_RUN_PREPARADO",
    "ERRO",
]


class FilledFieldReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    campo_logico: str
    seletor: str
    tipo: ApplicationFormFieldType
    preenchido: bool
    valor_preview: str = ""
    motivo_ignorado: str | None = None


class ApplicationPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    vaga_id: str = ""
    vaga_titulo: str
    empresa: str
    url_candidatura: str
    nome_completo: str
    primeiro_nome: str
    sobrenome: str
    email: str
    telefone: str = ""
    localizacao: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""
    curriculo_pdf_path: str | None = None
    carta_apresentacao: str = ""
    respostas_triagem: dict[str, str] = Field(default_factory=dict)


class CopilotSessionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: CopilotSessionStatus
    vaga_alvo: str
    url_destino: str
    submetido_automaticamente: Literal[False] = False
    requer_confirmacao_humana: bool = True
    perfil_navegador: str
    curriculo_pdf_path: str | None = None
    compatibilidade_horario: ScheduleFitResult
    campos_preenchidos: list[FilledFieldReport] = Field(default_factory=list)
    campos_pendentes_humano: list[str] = Field(default_factory=list)
    bloqueio_externo_detectado: str | None = None
    duplicata_detectada: bool = False
    aviso_seguranca: str
    proximos_passos_humano: list[str] = Field(default_factory=list)
