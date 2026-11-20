@echo off
chcp 65001 > nul
cls
echo =======================================================
echo          CAREER COPILOT — AGENTE DE CARREIRA
echo =======================================================
echo.
echo Escolha uma operacao:
echo [1] Diagnostico de Perfil e Viabilidade de Horario
echo [2] Minerar Vagas Internacionais e Nacionais (Top 10)
echo [3] Gerar Curriculo Customizado e Cold Pitch (Top 1)
echo [4] Banca Examinadora Cognitiva (7 Personas - Top 1)
echo [5] Compilar Curriculo em PDF A4 Corporativo (Top 1)
echo [6] Copiloto Assistido Human-in-the-Loop (Top 1)
echo [7] Executar Suite de Testes (Pytest)
echo [8] Sair
echo.
set /p op="Opcao: "

if "%op%"=="1" (
    python -m src.cli profile
    pause
) else if "%op%"=="2" (
    python -m src.cli mine --top 10
    pause
) else if "%op%"=="3" (
    python -m src.cli tailor --index 0
    pause
) else if "%op%"=="4" (
    python -m src.cli review --index 0
    pause
) else if "%op%"=="5" (
    python -m src.cli pdf --index 0
    pause
) else if "%op%"=="6" (
    python -m src.cli apply --index 0
    pause
) else if "%op%"=="7" (
    pytest
    pause
) else (
    exit /b
)
