import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from launch_options import add_launch_arguments, launch_mode, startup_config


def parse(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--configure-classroom', action='store_true')
    add_launch_arguments(parser)
    return launch_mode(parser.parse_args(argv))


@pytest.mark.parametrize(('argv', 'mode'), [([], 'auto'), (['--local'], 'demo'),
    (['--lan'], 'lan'), (['--configure-classroom'], 'lan')])
def test_mode(argv, mode):
    assert parse(argv) == mode


def test_modes_are_exclusive():
    with pytest.raises(SystemExit):
        parse(['--local', '--lan'])


def test_local_never_opens_setup():
    def setup(*args, **kwargs):
        pytest.fail('Local startup must not ask for a launch mode or classroom setup')
    assert startup_config(Path('example'), 'demo', setup) == {'demo': True}


def test_lan_and_auto_go_directly_to_login_before_admin_setup(tmp_path):
    def forbidden(*a,**kw):pytest.fail('Startup must not open a setup dialog')
    for mode in ('auto','lan'):
        config=startup_config(tmp_path,mode,forbidden,True)
        assert config['setup_complete'] is False and config['network_mode']=='setup'
        assert config['mode']=='server'


def test_saved_workstation_is_reused_without_setup(tmp_path):
    import json
    saved={'mode':'client','number':'12','server':'http://192.168.1.10:8765','token':'saved-token','station_id':'saved-id','setup_complete':True}
    (tmp_path/'classroom.json').write_text(json.dumps(saved))
    def forbidden(*a,**kw):pytest.fail('Saved configuration must not open a setup dialog')
    for mode in ('auto','lan'):
        result=startup_config(tmp_path,mode,forbidden)
        assert result['station_configured'] and result['setup_complete']
        assert result['token']=='saved-token' and result['number']=='12'
        assert not result.get('edit_connection')


@pytest.mark.parametrize(('flags', 'expected'), [([], 'auto'), (['--local'], 'demo'),
    (['--lan'], 'lan'), (['--configure-classroom'], 'lan')])
def test_launcher_passes_mode_to_window(monkeypatch, tmp_path, flags, expected):
    import os
    import desktop_launcher
    monkeypatch.setattr(sys, 'argv', ['Dispetcher112', '--data-dir', str(tmp_path), *flags])
    monkeypatch.setattr(desktop_launcher, 'configure', lambda data: None)
    monkeypatch.setenv('DESKTOP_LAUNCH_MODE', 'previous')
    monkeypatch.delenv('CONFIGURE_CLASSROOM', raising=False)
    calls = []
    monkeypatch.setattr(desktop_launcher, 'desktop',
                        lambda data: calls.append((data, os.environ['DESKTOP_LAUNCH_MODE'])))
    assert desktop_launcher.main() == 0
    assert calls == [(tmp_path.resolve(), expected)]


def test_existing_local_server_and_student_profiles(tmp_path):
    import importlib.util
    source = Path(__file__).resolve().parents[2] / 'apps/api/tests/test_desktop_profiles.py'
    spec = importlib.util.spec_from_file_location('desktop_profiles_regression', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.test_demo_reserves_one_server_and_isolated_reusable_clients(tmp_path)
