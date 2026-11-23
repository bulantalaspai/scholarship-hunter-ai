"""Start and supervise this checkout's loopback services on Windows."""

import argparse
import errno
import hashlib
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / ".local-run"
CHECKOUT = hashlib.sha256(os.path.normcase(str(ROOT)).encode()).hexdigest()[:24]
JOB = rf"Local\ScholarshipHunterAI.{CHECKOUT}.Services"
LOCK = rf"Local\ScholarshipHunterAI.{CHECKOUT}.Launcher"
MODEL = "qwen3:4b-instruct"
OLLAMA_PORT = 11434
URL = "http://localhost:5173"
HEALTH = {"service": "scholarship-hunter-ai", "status": "ok"}
STARTUP_TIMEOUT = 150


def read_http(port, path):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        if response.status == 200:
            return response.read(256_001)
    except OSError, http.client.HTTPException:
        pass
    finally:
        connection.close()
    return b""


def read_json(port, path):
    try:
        value = json.loads(read_http(port, path))
    except ValueError, UnicodeError:
        return {}
    return value if isinstance(value, dict) else {}


def ollama_running():
    return bool(read_json(OLLAMA_PORT, "/api/version").get("version"))


def model_installed():
    tags = read_json(OLLAMA_PORT, "/api/tags").get("models")
    return isinstance(tags, list) and any(
        isinstance(model, dict) and model.get("name") == MODEL for model in tags
    )


def frontend_ready():
    return (
        b"<title>Scholarship Hunter AI</title>" in read_http(5173, "/")
        and read_json(5173, "/api/health") == HEALTH
    )


def require_free_port(port, label):
    # Check both localhost address families before opening the browser by hostname.
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                probe.bind((host, port))
        except OSError as error:
            if family == socket.AF_INET6 and (
                getattr(error, "winerror", None) in (10047, 10049)
                or error.errno in (errno.EAFNOSUPPORT, errno.EADDRNOTAVAIL)
            ):
                continue
            raise RuntimeError(
                f"{label} port {port} is unavailable on {host}. Close the service "
                "using it or change the conflicting application's port."
            ) from error


def run_check(command, failure):
    print(f"Checking {Path(command[0]).name} {' '.join(command[1:])}", flush=True)
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(failure) from error
    if result.returncode:
        raise RuntimeError(failure)


def check_dependencies():
    if (
        sys.version_info[:2] != (3, 14)
        or Path(sys.prefix).resolve() != (ROOT / ".venv").resolve()
    ):
        raise RuntimeError("The repository's .venv must use Python 3.14.")
    node, npm = shutil.which("node.exe"), shutil.which("npm.cmd")
    if not node or not npm:
        raise RuntimeError(
            "Node.js 24 and npm must be installed and available on PATH."
        )
    version = subprocess.check_output(
        [node, "--version"], text=True, timeout=10
    ).strip()
    if not version.startswith("v24."):
        raise RuntimeError(f"Node.js 24 is required by package.json. Found {version}.")
    run_check(
        [sys.executable, "-m", "pip", "check"],
        r"Install Python dependencies with .\.venv\Scripts\python.exe -m pip "
        "install -r backend/requirements.txt.",
    )
    run_check(
        [sys.executable, "-c", "import uvicorn; import backend.app.main"],
        r"The API could not load. Run .\.venv\Scripts\python.exe -m pip "
        "install -r backend/requirements.txt and check launcher.log.",
    )
    vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
    if not vite.is_file():
        raise RuntimeError("Vite is missing. Run npm.cmd --prefix frontend ci.")
    run_check(
        [npm, "--prefix", "frontend", "ls", "--depth=0"],
        "Frontend dependencies are missing or inconsistent. "
        "Run npm.cmd --prefix frontend ci.",
    )
    return [node, str(vite)]


def prepare_database():
    # Use the application's path validation, schema and transactional importer.
    from sqlalchemy import select

    from backend.app.database import create_database_engine, initialize_database
    from backend.app.import_catalogue import import_catalogue, load_catalogue
    from backend.app.models import Scholarship

    catalogue = load_catalogue(ROOT / "backend/data/curated_scholarships.json")
    if catalogue.data_kind != "curated" or not catalogue.scholarships:
        raise RuntimeError(
            "The bundled curated scholarship catalogue is empty or invalid."
        )
    engine = create_database_engine()
    try:
        initialize_database(engine)
        with engine.begin() as connection:
            keys = select(Scholarship.identity_key)
            present = set(connection.scalars(keys))
            missing = [
                record
                for record in catalogue.scholarships
                if record.identity_key not in present
            ]
            if missing:
                # Bind the import to this transaction so any unexpected update
                # rolls back before reaching disk, even if another importer runs.
                result = import_catalogue(
                    connection, catalogue.model_copy(update={"scholarships": missing})
                )
                if result.updated:
                    raise RuntimeError(
                        "The catalogue changed during startup. Try again."
                    )
            present = set(connection.scalars(keys))
            expected = {record.identity_key for record in catalogue.scholarships}
            if not expected.issubset(present):
                raise RuntimeError(
                    "SQLite is missing expected curated scholarship records."
                )
        print(
            f"SQLite verified: {len(expected)} curated records, {len(present)} total.",
            flush=True,
        )
        return len(present)
    finally:
        engine.dispose()


def spawn_service(command, directory, name, run_dir, env=None):
    with (run_dir / f"{name}.log").open("ab") as log:
        return subprocess.Popen(
            command,
            cwd=directory,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )


def check_processes(processes):
    for name, process in processes.items():
        result = process.poll()
        if result is not None:
            raise RuntimeError(f"{name} exited with code {result}. Check {name}.log.")


def wait_ready(check, label, processes, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        check_processes(processes)
        if check():
            check_processes(processes)
            return
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {label}. Check the startup logs.")


def ensure_ollama(run_dir, processes):
    if not ollama_running():
        try:
            require_free_port(OLLAMA_PORT, "Ollama")
        except RuntimeError:
            # An existing desktop Ollama service may still be initializing.
            wait_ready(
                ollama_running,
                f"the existing service on Ollama port {OLLAMA_PORT}",
                {},
                8,
            )
        else:
            installed = (
                Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe"
            )
            ollama = shutil.which("ollama.exe") or (
                str(installed) if installed.is_file() else None
            )
            if not ollama:
                raise RuntimeError(
                    "Install Ollama for Windows or start its existing installation."
                )
            env = os.environ | {"OLLAMA_HOST": f"127.0.0.1:{OLLAMA_PORT}"}
            processes["ollama"] = spawn_service(
                [ollama, "serve"], ROOT, "ollama", run_dir, env
            )
            wait_ready(ollama_running, f"Ollama on port {OLLAMA_PORT}", processes)
    if not model_installed():
        if not isinstance(read_json(OLLAMA_PORT, "/api/tags").get("models"), list):
            raise RuntimeError(
                "Ollama responded, but its installed model list could not be read."
            )
        raise RuntimeError(
            f"Model {MODEL} is missing. Run ollama pull {MODEL} and retry."
        )
    print(f"Ollama is ready with {MODEL}.", flush=True)


def supervise(run_dir):
    from windows_job import own_process_tree

    try:
        own_process_tree(JOB)
        require_free_port(8000, "FastAPI")
        require_free_port(5173, "Vite")
        vite = check_dependencies()
        processes = {}
        ensure_ollama(run_dir, processes)
        expected_total = prepare_database()
        processes["backend"] = spawn_service(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            ROOT,
            "backend",
            run_dir,
        )
        wait_ready(
            lambda: read_json(8000, "/api/health") == HEALTH,
            "the FastAPI health check",
            processes,
        )
        wait_ready(
            lambda: (
                read_json(8000, "/api/scholarships?page_size=1").get("total")
                == expected_total
            ),
            "the FastAPI SQLite catalogue",
            processes,
        )
        processes["frontend"] = spawn_service(
            vite, ROOT / "frontend", "frontend", run_dir
        )
        wait_ready(frontend_ready, "the Vite page and API proxy", processes)
        (run_dir / "ready").touch()
        print("Application ready.", flush=True)
        while True:
            check_processes(processes)
            time.sleep(0.5)
    except Exception as error:
        detail = run_dir / "error.tmp"
        detail.write_text(str(error), encoding="utf-8")
        detail.replace(run_dir / "error.txt")
        traceback.print_exc()
        return 1


def start(no_browser):
    from windows_job import managed_job

    if managed_job(JOB):
        wait_ready(frontend_ready, "the existing launcher session", {}, 8)
        if not model_installed():
            raise RuntimeError(
                "The existing session cannot reach the installed Ollama model."
            )
        print(f"Already running. Logs are under {LOGS}")
    else:
        run_dir = LOGS / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
        run_dir.mkdir(parents=True)
        print(f"Starting Scholarship Hunter AI. Logs: {run_dir}", flush=True)
        process = spawn_service(
            [
                sys.executable,
                "-u",
                str(Path(__file__).resolve()),
                "supervise",
                str(run_dir),
            ],
            ROOT,
            "launcher",
            run_dir,
        )
        try:
            deadline = time.monotonic() + STARTUP_TIMEOUT
            while time.monotonic() < deadline:
                error_file = run_dir / "error.txt"
                if error_file.is_file():
                    raise RuntimeError(error_file.read_text(encoding="utf-8"))
                if process.poll() is not None:
                    raise RuntimeError("Startup controller exited. Check launcher.log.")
                if (run_dir / "ready").exists():
                    break
                time.sleep(0.25)
            else:
                raise RuntimeError("Startup timed out. Check launcher.log.")
        except Exception, KeyboardInterrupt:
            if not managed_job(JOB, stop=True) and process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
            raise
    print(f"Ready at {URL}")
    if not no_browser:
        os.startfile(URL)


def stop():
    from windows_job import managed_job

    if not managed_job(JOB, stop=True):
        print("No launcher-managed services are running for this checkout.")
        return
    deadline = time.monotonic() + 10
    while managed_job(JOB):
        if time.monotonic() >= deadline:
            raise RuntimeError("Timed out waiting for the launcher services to stop.")
        time.sleep(0.1)
    print("Launcher-managed services stopped.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    launch = actions.add_parser("start")
    launch.add_argument("--no-browser", action="store_true")
    actions.add_parser("stop")
    worker = actions.add_parser("supervise")
    worker.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    if os.name != "nt":
        parser.exit(1, "The local launcher requires Windows.\n")
    from windows_job import launcher_lock

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    try:
        if args.action == "supervise":
            return supervise(args.run_dir)
        with launcher_lock(LOCK):
            if args.action == "start":
                start(args.no_browser)
            else:
                stop()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Scholarship Hunter AI: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
