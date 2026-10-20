"""Four packaged cases extend the two practice tickets to a six-ticket library."""
import json
from sqlalchemy import select
from .db import ROOT, User, Ticket, TicketVersion
from .schemas import TicketData


def cases():
    path = ROOT / 'content' / 'starter-tickets.json'
    return [TicketData.model_validate(item).model_dump()
            for item in json.loads(path.read_text(encoding='utf-8'))]


def seed(db):
    from .voice import prepare
    owner = db.scalar(select(User).where(User.role == 'admin'))
    if not owner:
        return
    existing = {task.get('id') for version in db.scalars(select(TicketVersion))
                for task in version.data.get('tasks', [])}
    for data in cases():
        if data['tasks'][0]['id'] in existing:
            continue
        ticket = Ticket(title=data['title'], created_by=owner.id)
        db.add(ticket)
        db.flush()
        db.add(TicketVersion(ticket_id=ticket.id, number=1, published=True,
                             data=prepare(data, db, owner.id)))
    db.commit()
