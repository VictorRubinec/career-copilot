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
echo [4] Executar Suite de Testes (Pytest)
echo [5] Sair
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
    pytest
    pause
) else (
    exit /b
)
