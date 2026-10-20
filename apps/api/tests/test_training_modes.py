from test_flows import app, TestClient, login, post


def test_admin_switch_limits_dds_catalogs_and_can_restore_112():
    with TestClient(app) as client:
        login(client, 'admin')
        before = client.get('/api/management/training-modes').json()['operator112']
        try:
            assert post(client, '/management/training-modes', {'operator112': False}).status_code == 200
            assert all(all(t['mode'] == 'dds' for t in v['data']['tasks']) for v in client.get('/api/tickets').json())
            assert all(q.get('mode', 'dds') == 'dds' for q in client.get('/api/learning/questions').json())
            assert post(client, '/ai/wizard', {'mode': '112', 'incident_type': 'пожар', 'services': ['ДДС района']}).status_code == 400
            login(client, 'teacher')
            assert post(client, '/management/training-modes', {'operator112': True}).status_code == 403
            login(client, 'student')
            assert all(t['mode'] == 'dds' for t in client.get('/api/tutorials').json())
            assert all(all(t['mode'] == 'dds' for t in a['tasks']) for a in client.get('/api/assignments').json())
            assert all(p['task']['mode'] == 'dds' for p in client.get('/api/results').json())
            login(client, 'admin')
            assert post(client, '/management/training-modes', {'operator112': True}).status_code == 200
            assert any(t['mode'] == '112' for t in client.get('/api/tutorials').json())
        finally:
            login(client, 'admin')
            post(client, '/management/training-modes', {'operator112': before})
