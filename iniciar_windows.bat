@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Handwave

where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 (
    echo Python 3.10 ou superior não foi encontrado.
    echo Instale em https://www.python.org/downloads/ e marque a opção "Add python.exe to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Criando o ambiente virtual...
    %PY% -m venv .venv
    if errorlevel 1 goto erro
)

echo Conferindo as dependências...
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check --upgrade pip
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto erro

echo Abrindo o Handwave...
".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
exit /b 0

:erro
echo.
echo Não foi possível preparar o Handwave. Confira a conexão com a internet e tente de novo.
pause
exit /b 1
