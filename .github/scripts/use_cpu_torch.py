"""
Makes `requirements.txt` install the CPU build of PyTorch, which is a fraction of
the size of the CUDA one. The workflows only need it to run the tests and to check
that the app can be built.
"""

from pathlib import Path

CUDA_INDEX = "https://download.pytorch.org/whl/cu128"
CPU_INDEX = "https://download.pytorch.org/whl/cpu"

requirements = Path(__file__).parents[2] / "requirements.txt"
content = requirements.read_text(encoding="utf-8")

if CUDA_INDEX not in content:
    raise SystemExit(f"{CUDA_INDEX} not found in {requirements}")

requirements.write_text(content.replace(CUDA_INDEX, CPU_INDEX), encoding="utf-8")
print(f"{requirements.name} now uses {CPU_INDEX}")
