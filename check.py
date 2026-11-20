"""Run every project's independent unittest suite, from any working directory."""

import os
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    projects = sorted(folder for folder in root.iterdir() if folder.is_dir() and (folder / "README.md").is_file())
    if len(projects) != 10:
        raise SystemExit(f"Expected ten projects, found {len(projects)}")
    failures = []
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    for folder in projects:
        if not any(folder.glob("test_*.py")):
            raise SystemExit(f"No tests in {folder.name}")
        print(f"\n[{folder.name}]", flush=True)
        result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-v"], cwd=folder, env=env)
        if result.returncode:
            failures.append(folder.name)
    if failures:
        raise SystemExit(f"Failing suites: {', '.join(failures)}")
    print(f"\nAll {len(projects)} project suites passed.")


if __name__ == "__main__":
    main()
