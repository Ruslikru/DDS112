"""Exercise the packaged speech worker with Unicode model and recording paths."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import wave

parser = argparse.ArgumentParser()
parser.add_argument('--bundle', type=Path, required=True)
parser.add_argument('--worker', type=Path)
parser.add_argument('--report', type=Path)
args = parser.parse_args()
bundle = args.bundle.resolve()
folder = Path(tempfile.mkdtemp(prefix='Проверка голоса — ', dir=Path(__file__).resolve().parents[1] / 'build'))
recording = folder / 'Готовая запись.wav'
requests = [
    dict(op='warm', model='gigaam', device='cpu'),
    dict(op='synthesize', model='piper-denis', device='cpu', text='Проверка связи. Мы прибыли.', output=str(recording)),
    dict(op='transcribe', model='gigaam', device='cpu', input=str(recording)),
]
result = subprocess.run([
    str(bundle / 'local_ai/voice/runtime/python.exe'), '-u',
    str((args.worker or bundle / 'local_ai/voice_worker.py').resolve()),
    str(bundle / 'local_ai/voice/models'),
], input=''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in requests),
    text=True, encoding='utf-8', capture_output=True, timeout=120,
    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
assert result.returncode == 0, result.stderr
responses = [json.loads(line) for line in result.stdout.splitlines()]
assert len(responses) == 3 and all(row.get('ok') for row in responses), responses
assert 'прибыли' in responses[-1]['text'].lower(), responses[-1]
with wave.open(str(recording), 'rb') as audio:
    assert audio.getnframes() > 0
report = dict(ready=True, bundle=str(bundle), recording=str(recording), responses=responses)
if args.report:
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
