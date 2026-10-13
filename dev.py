from pathlib import Path

from watchfiles import PythonFilter, run_process

ROOT = Path(__file__).resolve().parent


def run_app():
    import main

    main.main()


def on_change(changes):
    names = sorted({Path(path).name for _, path in changes})
    print(f"Alterado: {', '.join(names)}. Reiniciando o Handwave.", flush=True)


if __name__ == "__main__":
    print("Modo de desenvolvimento ativo. Salve um arquivo .py para recarregar. Ctrl+C para sair.", flush=True)
    run_process(ROOT, target=run_app, callback=on_change, watch_filter=PythonFilter(), debounce=400)
