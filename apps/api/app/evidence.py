"""Separate authored records, spoken answers and received facts for grading."""
from datetime import datetime


def is_learner(message):
    role = message.get('actor_role')
    if role:
        return role == 'learner'
    # Old attempts did not store roles. Exact UI labels are safe; a contact named
    # "Диспетчер другой службы" is not the learner.
    who = message.get('who', '').strip()
    return who in ('Оператор', 'Диспетчер') or who.startswith(('Диспетчер → ', 'Оператор → '))


def before(left, right):
    """Unknown time cannot establish that a report preceded a status."""
    try:
        return datetime.fromisoformat(left).timestamp() <= datetime.fromisoformat(right).timestamp()
    except (TypeError, ValueError):
        return False


def received_reports(state):
    return [m for m in state.get('messages', [])
            if not is_learner(m) and (m.get('report_id') or m.get('stage_id'))
            and m.get('actor_role') not in ('system', 'teacher')]


def matches_report(message, criterion):
    if criterion.get('report_id'):
        return message.get('report_id') == criterion['report_id']
    return bool(criterion.get('stage_id')) and message.get('stage_id') == criterion['stage_id']


def status_evidence(state, task, criterion):
    rows = [h for h in state.get('services', {}).get(task['own_service'], [])
            if h.get('status') == criterion['expected']
            and h.get('actor_role', 'learner') == 'learner'
            and not h.get('comment_only')]
    if not criterion.get('report_id') and not criterion.get('stage_id'):
        return bool(rows), ''
    reports = [m for m in received_reports(state) if matches_report(m, criterion)]
    if any(before(m.get('at'), h.get('at')) for h in rows for m in reports):
        return True, ''
    return False, ('Статус выбран до получения соответствующего доклада.'
                   if rows else 'Статус не установлен.')


def written_records(state, task, criterion):
    rows = [h for h in state.get('services', {}).get(task['own_service'], [])
            if h.get('actor_role', 'learner') == 'learner' and h.get('comment', '').strip()
            and (h.get('actor_role') or h.get('status') not in ('Добавлена','Получена службой'))]
    if criterion.get('stage_id') or criterion.get('report_id'):
        # A stage-specific criterion cannot be satisfied by an unrelated comment.
        rows = [h for h in rows if matches_report(h, criterion)
                or (not h.get('report_id') and not h.get('stage_id')
                    and criterion.get('status') and h.get('status') == criterion['status'])]
        reports = [m for m in received_reports(state) if matches_report(m, criterion)]
        rows = [h for h in rows if any(before(m.get('at'), h.get('at')) for m in reports)]
    elif criterion.get('status'):
        rows = [h for h in rows if h.get('status') == criterion['status']]
    return rows


def speech_messages(state, task, criterion=None):
    dialogue = state.get('dialogue', []) if task['mode'] == '112' else state.get('messages', [])
    if not criterion or not (criterion.get('stage_id') or criterion.get('report_id')):
        return [m for m in dialogue if is_learner(m)]
    selected = []
    active = False
    contact = None
    for message in dialogue:
        if not is_learner(message) and (message.get('report_id') or message.get('stage_id')):
            if matches_report(message, criterion):
                active = True
                contact = message.get('contact_id')
            elif active and (not contact or message.get('contact_id') == contact):
                active = False
        elif active and is_learner(message):
            if not contact or not message.get('contact_id') or message['contact_id'] == contact:
                selected.append(message)
        if active and message.get('call_end') and (not contact or message.get('contact_id') == contact):
            active = False
    return selected


def speech_context(state, task, selected):
    """Only facts already received at each utterance; never future scenario events."""
    dialogue = state.get('dialogue', []) if task['mode'] == '112' else state.get('messages', [])
    turns = []
    known = []
    for message in dialogue:
        if not is_learner(message):
            if message.get('text'):
                known.append({'text': message['text'], 'who': message.get('who', ''),
                              'report_id': message.get('report_id', '')})
        elif any(message is item for item in selected):
            records = [{'service': service, 'status': h.get('status', ''), 'comment': h['comment']}
                       for service, rows in state.get('services', {}).items() for h in rows
                       if service != task.get('own_service') and h.get('comment')
                       and before(h.get('at'), message.get('at'))]
            turns.append({'learner_text': message.get('text', ''),
                          'received_before_reply': list(known), 'available_service_records': records})
    return {'mode': task['mode'], 'card': task.get('initial_card', {}) if task['mode'] == 'dds' else {},
            'turns': turns,
            'availability_rule': 'Оценивайте каждую реплику только по сведениям, доступным до неё. '
            'Будущие доклады не являются основанием. Если данных нет, честное сообщение об их отсутствии допустимо. '
            'Если маршрут уже есть в доступной истории службы, ответ «не знаю» не заменяет поиск сведений.'}
