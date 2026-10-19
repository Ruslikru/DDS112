from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from test_flows import app

from apps.api.app.test_catalog import TITLES, available, enabled, versions


def test_default_catalog_and_full_switch(monkeypatch):
    monkeypatch.delenv('TRAINING_CATALOG', raising=False)
    assert not enabled()
    assert available({'tasks': [{'mode': 'dds', 'title': TITLES[0]}]})
    assert available({'tasks': [{'mode': '112', 'title': TITLES[0]}]})
    assert available({'tasks': [{'mode': 'dds', 'title': 'Другой билет'}]})
    monkeypatch.setenv('TRAINING_CATALOG', 'full')
    assert not enabled()
    assert available({'tasks': [{'mode': '112', 'title': 'Другой билет'}]})


def test_catalog_keeps_latest_two_and_lesson_snapshots(monkeypatch):
    monkeypatch.setenv('TRAINING_CATALOG', 'two-dds')
    latest = SimpleNamespace(data={'title': TITLES[0], 'tasks': [{'mode': 'dds', 'title': TITLES[0]}]})
    older = SimpleNamespace(data=latest.data)
    second = SimpleNamespace(data={'title': TITLES[1], 'tasks': [{'mode': 'dds', 'title': TITLES[1]}]})
    snapshot = SimpleNamespace(data={**latest.data, 'description': 'Снимок занятия'})
    assert list(versions([snapshot, latest, older, second])) == [latest, second]
    assert available({'title': 'Снимок занятия', 'tasks': latest.data['tasks'] + second.data['tasks']})


def test_fresh_and_existing_catalog_end_to_end():
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run([sys.executable, '-X', 'utf8', str(root / 'scripts/check_two_dds_catalog.py')],
                            cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS:' in result.stdout
