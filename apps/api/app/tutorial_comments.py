"""Immediate training feedback; full free-text assessment remains in the AI review."""
import re

RULES={
 'Начало реагирования':(r'вые(х|з)|выезд|направ|отправ','Укажите, что бригада выехала или направлена по заявке.'),
 'Прибытие':(r'приб(ы|и)|на месте','Запишите доклад о прибытии бригады на место.'),
 'Проведение работ':(r'работ|ремонт|провер|устраня|перекры','Укажите, какие работы или проверку выполняет бригада.'),
 'Работы завершены':(r'заверш|устранен|ликвидир|восстанов','Запишите результат: что устранено и что работы завершены.'),
}

def feedback(status,comment):
    rule=RULES.get(status)
    if not rule:return None
    normalized=comment.strip().casefold().replace('ё','е')
    if not re.search(rule[0],normalized) or re.search(r'\bне\s+(принят|прибыл|выехал|заверш|устранен)',normalized):return rule[1]
    return None
