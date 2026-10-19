"""Run with local_ai/voice/runtime/python.exe: the speech runtime must be self-contained.

Fails when any import path leaves the runtime folder (for example a .pth file that
points to a developer virtualenv) or when a module used by voice_worker.py is missing.
"""
import importlib
import sys
from pathlib import Path

REQUIRED = ('numpy', 'torch', 'torchaudio', 'soundfile', 'av', 'hydra', 'sentencepiece', 'piper', 'onnxruntime')

runtime = Path(sys.prefix).resolve()
site = runtime / 'Lib' / 'site-packages'
errors = []

for pth in sorted(site.glob('*.pth')):
    for line in pth.read_text('utf-8', errors='replace').splitlines():
        line = line.strip()
        if not line or line.startswith(('#', 'import ', 'import\t')):
            continue
        target = Path(line) if Path(line).is_absolute() else site / line
        if not target.resolve().is_relative_to(runtime):
            errors.append(f'{pth.name}: path outside the runtime: {line}')

here = Path(__file__).resolve().parent
for entry in sys.path:
    if entry and Path(entry).resolve() != here and not Path(entry).resolve().is_relative_to(runtime):
        errors.append(f'sys.path entry outside the runtime: {entry}')

for name in REQUIRED:
    try:
        module = importlib.import_module(name)
    except Exception as exc:
        errors.append(f'cannot import {name}: {exc}')
        continue
    origin = getattr(module, '__file__', None)
    if origin and not Path(origin).resolve().is_relative_to(runtime):
        errors.append(f'{name} loaded from outside the runtime: {origin}')

if errors:
    print('Voice runtime is not self-contained:', *errors, sep='\n  ', file=sys.stderr)
    sys.exit(1)
print(f'Voice runtime is self-contained: {runtime}')
