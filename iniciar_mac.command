#!/bin/bash
cd "$(dirname "$0")" || exit 1

fail() {
    echo
    echo "$1"
    read -r -n 1 -p "Pressione qualquer tecla para fechar."
    exit 1
}

PY=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
        "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
        PY="$candidate"
        break
    fi
done
[ -n "$PY" ] || fail "Python 3.10 ou superior não foi encontrado. Instale em https://www.python.org/downloads/"

if [ ! -x ".venv/bin/python" ]; then
    echo "Criando o ambiente virtual..."
    "$PY" -m venv .venv || fail "Não foi possível criar o ambiente virtual."
fi

echo "Conferindo as dependências..."
.venv/bin/python -m pip install -q --disable-pip-version-check --upgrade pip
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt ||
    fail "Não foi possível instalar as dependências. Confira a conexão com a internet e tente de novo."

echo "Abrindo o Handwave..."
exec .venv/bin/python main.py
