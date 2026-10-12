"""Create an isolated environment without changing the main server packages."""
import os
from pathlib import Path
import subprocess
import venv
root = Path(__file__).resolve().parents[1]
directory = root / ".venv-minicpm"
venv.EnvBuilder(with_pip=True, system_site_packages=True).create(directory)
python = directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
subprocess.run([str(python), "-m", "pip", "install", "-r", str(root / "requirements-minicpm.txt")], check=True)
print("MiniCPM 환경 설치 완료:", python)
