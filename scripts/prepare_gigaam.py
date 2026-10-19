"""Скачать фиксированную версию GigaAM в комплект сборки, без загрузок на рабочих ПК."""
from pathlib import Path

from huggingface_hub import snapshot_download


MODEL = 'ai-sage/GigaAM-v3'
REVISION = 'cec030b4c4f35d928e4a9044a3bdb29ebd499fac'  # e2e_ctc
FILES = ('config.json', 'modeling_gigaam.py', 'pytorch_model.bin', 'tokenizer.model')
TARGET = Path(__file__).resolve().parents[1] / 'local_ai' / 'voice' / 'models' / 'gigaam'


def complete() -> bool:
    return all((TARGET / name).is_file() for name in FILES) and (TARGET / 'pytorch_model.bin').stat().st_size == 442405251


if __name__ == '__main__':
    if not complete():
        if TARGET.exists():
            raise SystemExit(f'Папка модели неполная: {TARGET}. Проверьте её перед повторной сборкой.')
        snapshot_download(MODEL, revision=REVISION, local_dir=TARGET, allow_patterns=(*FILES, 'README.md'))
        if not complete():
            raise SystemExit(f'Не удалось подготовить модель: {TARGET}')
    print(f'GigaAM готова для упаковки: {TARGET}')
