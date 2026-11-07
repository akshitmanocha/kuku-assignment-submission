"""Start an isolated local server, check it, and always stop the owned process."""

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def run(browser=False):
    # Bind to zero only to find a free port. The child owns the actual listener.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="promo-lab-checks-") as directory:
        work = Path(directory)
        env = os.environ | {"PROMO_TEST_URL": f"http://127.0.0.1:{port}", "PYTHONPATH": str(ROOT)}
        # Use a temporary storage root rather than the user's live experiment DB.
        command = [
            sys.executable,
            "-c",
            "from pathlib import Path; from promo_lab.server import serve_app; import sys; serve_app(Path(sys.argv[1]),int(sys.argv[2]))",
            str(work),
            str(port),
        ]
        with (work / "server.log").open("w+") as log:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError("Test server exited: " + log.read())
                    try:
                        with urlopen(env["PROMO_TEST_URL"] + "/api/status", timeout=1):
                            break
                    except (URLError, TimeoutError):
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Test server did not become ready")
                if browser:
                    for script in (
                        "browser_smoke.mjs",
                        "experiment_smoke.mjs",
                        "simulation_smoke.mjs",
                    ):
                        subprocess.run(
                            ["node", str(ROOT / "scripts" / script)], cwd=ROOT, env=env, check=True
                        )
                else:
                    subprocess.run(
                        [sys.executable, str(ROOT / "scripts/http_smoke.py")],
                        cwd=ROOT,
                        env=env,
                        check=True,
                    )
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", action="store_true", help="Run optional Playwright checks")
    run(parser.parse_args().browser)
