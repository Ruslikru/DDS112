import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3


def export_catalog(sources, destination):
    destination.mkdir(parents=True, exist_ok=False)
    catalog = {}
    inspected = []
    for source in sorted(sources, key=lambda path: path.stat().st_mtime):
        with sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True) as database:
            database.row_factory = sqlite3.Row
            rows = database.execute('SELECT t.id, t.title, t.archived, v.id AS version_id, v.number, v.published, v.data FROM tickets t JOIN ticket_versions v ON v.ticket_id=t.id ORDER BY t.id,v.number').fetchall()
            inspected.append({'path': str(source), 'versions': len(rows)})
            for row in rows:
                data = json.loads(row['data'])
                title = row['title']
                previous = catalog.get(title, {})
                locations = previous.get('sources', [])
                location = str(source)
                if location not in locations:
                    locations.append(location)
                catalog[title] = {'title': title, 'sources': locations, 'ticket_id': row['id'], 'version_id': row['version_id'],
                                  'number': row['number'], 'published': bool(row['published']), 'archived': bool(row['archived']), 'data': data}
    items = sorted(catalog.values(), key=lambda item: item['title'].casefold())
    payload = {'exported_at': datetime.now(timezone.utc).isoformat(), 'selection': 'Все уникальные названия из основной базы и локальных demo-профилей. Для каждого названия — последняя прочитанная версия из наиболее недавно изменённой базы. Это каталог для тестов, не резервная копия всех исторических версий.',
               'source_databases': inspected, 'ticket_count': len(items), 'tickets': items}
    with (destination / 'catalog.json').open('x', encoding='utf-8') as output:
        json.dump(payload, output, ensure_ascii=False, indent=2)
    with (destination / 'catalog.md').open('x', encoding='utf-8') as output:
        output.write('# Полный каталог билетов перед сокращением\n\n')
        output.write(f'Уникальных названий: **{len(items)}**. Проверено баз: **{len(inspected)}**.\n\n')
        output.write(payload['selection'] + '\n\nЭкспорт содержит только билеты, без учётных записей, паролей и результатов учеников. JSON сохраняет полные данные выбранных версий. Источники — основная база приложения и локальные демонстрационные профили. Режимы 112 и ДДС указаны отдельно; похожие происшествия в разных режимах — разные билеты.\n\n')
        output.write('## Список\n\n| № | Билет | Режимы | Заданий |\n|---|---|---|---|\n')
        for index, item in enumerate(items, 1):
            tasks = item['data'].get('tasks', [])
            modes = ', '.join(dict.fromkeys('ДДС' if task.get('mode') == 'dds' else str(task.get('mode', '')) for task in tasks))
            output.write(f"| {index} | {item['title'].replace('|', '/')} | {modes} | {len(tasks)} |\n")
        for index, item in enumerate(items, 1):
            output.write(f"\n## {index}. {item['title']}\n\n")
            description = item['data'].get('description', '')
            if description:
                output.write(description + '\n\n')
            for task in item['data'].get('tasks', []):
                output.write('### ' + task.get('title', 'Задание') + '\n\n')
                output.write('Режим: ' + str(task.get('mode', '')) + '. Своя служба: ' + str(task.get('own_service', '')) + '.\n\n')
                output.write('Первое сообщение:\n\n' + str(task.get('intro', '')) + '\n\n')
                for field, label in [('initial_card', 'Входящая карточка'), ('expected_card', 'Ожидаемая карточка'), ('questions', 'Вопросы и ответы'), ('contacts', 'Контакты и реплики'), ('service_events', 'Звонки и события'), ('criteria', 'Критерии')]:
                    if task.get(field):
                        output.write('**' + label + '**\n\n```json\n' + json.dumps(task[field], ensure_ascii=False, indent=2) + '\n```\n\n')
    checks = []
    for name in ['catalog.json', 'catalog.md']:
        file = destination / name
        checks.append({'file': name, 'bytes': file.stat().st_size, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
    with (destination / 'manifest.json').open('x', encoding='utf-8') as output:
        json.dump({'status': 'verified', 'ticket_count': len(items), 'files': checks}, output, indent=2)
    assert len(json.loads((destination / 'catalog.json').read_text(encoding='utf-8'))['tickets']) == len(items)
    return len(items), len(inspected)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, default=Path(os.environ['LOCALAPPDATA']) / 'Dispetcher112')
    args = parser.parse_args()
    sources = [args.data_root / 'dispetcher.db'] + list((args.data_root / 'demo').rglob('dispetcher.db'))
    sources = [file for file in sources if file.is_file()]
    if not sources:
        raise SystemExit('Не найдены базы приложения; экспорт не создан')
    print(export_catalog(sources, args.output), str(args.output))
