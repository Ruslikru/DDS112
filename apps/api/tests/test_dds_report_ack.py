import pytest
from local_ai.dds_dialogue import reply

@pytest.mark.parametrize('report,text,end',[
 ('Мы прибыли. Обстановка соответствует заявке.','Принял, приступайте к работам, доложите о завершении.',True),
 ('Мы прибыли. Обстановка соответствует заявке.','Прибытие зафиксировано, работайте.',True),
 ('Мы прибыли. Обстановка соответствует заявке.','Понял.',True),
 ('Работы завершены. Опасность устранена.','Ну всё, молодцы, ждём вас на базе.',True),
 ('Работы завершены. Опасность устранена.','Спасибо, возвращайтесь.',True),
 ('Мы прибыли. Обстановка соответствует заявке.','Принял, а пострадавшие есть?',False),
 ('Мы прибыли. Обстановка не соответствует заявке.','Принял.',False),
 ('Работы не завершены, опасность сохраняется.','Принял.',False),
 ('Стоим в пробке.','Принял.',False),
 ('Мы прибыли. Обстановка соответствует заявке.','Не приступайте к работам.',False),
])
def test_report_acknowledgement_controls_call_end(report,text,end):
 contact={'id':'brigade','name':'Старший бригады','response':'Выезжаем.'}
 state={'messages':[{'who':'Старший бригады','text':report,'contact_id':'brigade','direction':'incoming'}],'contact_counts':{'brigade':1}}
 calls=[]
 def complete(*a,**k):calls.append(a);return {'text':'Уточните распоряжение.'},{'model':'test'}
 result=reply(text,{},contact,state,[],complete)
 assert result['call_end'] is end
 if end:assert not calls
