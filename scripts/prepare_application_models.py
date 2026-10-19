"""Copy the verified 1000-step Qwen adapter and its exact base into the app bundle."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_ai.model_catalog import ASSISTANT_MODEL, ASSISTANT_ADAPTER


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    lab = ROOT / 'ai_lab/qwen_training/chat_lab/models'
    ready = json.loads((lab / '1000-ready.json').read_text('utf-8'))
    base_dir = ROOT / 'ai_lab/models/qwen25-15b'
    base = json.loads((base_dir / 'manifest.json').read_text('utf-8'))
    if not ready.get('verified') or ready.get('steps') != 1000 or not ready.get('cpu_loaded'):
        raise RuntimeError('The 1000-step adapter has not passed export verification')
    file = base['files'][0]
    sources = [(base_dir / file['file'], ASSISTANT_MODEL, file['sha256']),
               (lab / 'qwen-dds-1000-f32.gguf', ASSISTANT_ADAPTER, ready['gguf_sha256'])]
    for source, relative, digest in sources:
        if sha256(source) != digest:
            raise RuntimeError(f'Source checksum mismatch: {source}')
        target = ROOT / 'local_ai' / relative
        if target.exists():
            if sha256(target) != digest:
                raise RuntimeError(f'Different weights already exist: {target}')
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        if sha256(target) != digest:
            raise RuntimeError(f'Copied checksum mismatch: {target}')
        print(f'Verified: {relative}', flush=True)
    manifest_path = ROOT / 'local_ai/manifest.json'
    manifest = json.loads(manifest_path.read_text('utf-8'))
    manifest.pop('alternative_models', None)
    manifest['assistant'] = {
        'model': 'Qwen2.5-1.5B-Instruct', 'training_steps': 1000,
        'dataset': ready['dataset'], 'file': ASSISTANT_MODEL,
        'bytes': file['bytes'], 'sha256': file['sha256'],
        'source': f"https://huggingface.co/{base['repo']}", 'revision': base['revision'],
        'adapter': {'file': ASSISTANT_ADAPTER, 'bytes': ready['bytes'],
                    'sha256': ready['gguf_sha256'], 'source_sha256': ready['source_sha256']},
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf-8')


if __name__ == '__main__':
    main()
