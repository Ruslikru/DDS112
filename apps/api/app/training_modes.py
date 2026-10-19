"""Доступные учебные роли; старые билеты сохраняются при смене режима."""
from .management_models import ManagementSetting


def operator_112_enabled(db):
    row = db.get(ManagementSetting, 'training_modes')
    return bool(row and (row.value or {}).get('operator112', False))
