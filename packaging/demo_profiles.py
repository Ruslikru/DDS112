"""Isolated, reusable profiles for multiple native windows on one machine."""
import json
import uuid
DEMO_PASSWORD = '12345678'


def reserve(base, acquire, close, verify):
    url = 'http://127.0.0.1:8765'
    folder = base / 'demo' / 'server'
    handle, busy = acquire(folder)
    if not busy and not verify(url):
        run_dir=base / 'demo' / 'runs' / uuid.uuid4().hex
        run_dir.mkdir(parents=True, exist_ok=False)
        config={'mode':'server','number':'Демо сервер','server':url,'name':'Учебный класс','demo':True}
        return run_dir, config, handle
    close(handle)
    for number in range(1, 251):
        folder = base / 'demo' / f'client-{number}'
        handle, busy = acquire(folder)
        if busy:
            close(handle)
            continue
        folder.mkdir(parents=True, exist_ok=True)
        file = folder / 'classroom.json'
        config = json.loads(file.read_text('utf-8')) if file.exists() else {}
        # A newly opened demo window joins the classroom only after explicit setup.
        config['station_configured']=False;config['server_selected']=False
        station_number=f'Демо слот {number}'
        config.update(mode='client', number=station_number, server=url, demo=True)
        return folder, config, handle
    raise RuntimeError('Достигнут лимит одновременно открытых рабочих мест.')
