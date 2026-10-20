from apps.api.app.classifier_routing import matrix, resolve, flags


def fire(**changes):
    return {'incident_type':'пожар: мусор','city':'Москва','victims':'no',**changes}


def test_matrix_preserves_all_codes_and_exclusion_notes():
    data=matrix()
    assert len(data['rows'])==1281
    assert len({r['code'] for r in data['rows']})==1281
    assert len(data['columns'])==76
    notes=[cell['note'] for row in data['rows'] for cell in row['cells'].values() if cell.get('note')]
    assert len(notes)==842
    assert data['source']['sha256']=='8d969b8e973a9574c63763ff290a11cb7221c50e5f9955efdb33520914d51409'


def test_conditional_victims_and_gas_are_not_always_dispatched():
    base=resolve(fire())
    selected=resolve(fire(victims='yes',traits=['Газифицированный дом']))
    assert 'Служба 103' not in base['services']
    assert 'Служба 104' not in base['services']
    assert {'Служба 101','Служба 102','Служба 103','Служба 104'} <= set(selected['services'])
    assert any(e['cell']=='Z5' for e in selected['entries'])
    assert all(e['cell']!='AA5' for e in selected['entries'])


def test_unknown_victims_need_review_not_assumed_absent():
    result=resolve(fire(victims='unknown'))
    assert any(e['cell']=='Z5' for e in result['unresolved'])
    assert 'Служба 103' not in result['services']
    assert result['warning']


def test_explicit_no_access_enables_conditional_rescue():
    result=resolve(fire(traits=['Нет доступа']))
    assert any(e['cell']=='T5' for e in result['entries'])
    assert flags({'description':'Дом не газифицирован. Газовой плиты нет.'})['gas'] is False


def test_excluded_cells_never_reintroduced_by_routing():
    data=matrix()
    row=next(r for r in data['rows'] if r['row']==34)
    result=resolve({'classifier_code':row['code'],'city':'Москва','victims':'yes'})
    assert any(e['cell']=='AZ34' and e.get('note') for e in result['excluded'])
    assert all(e['cell']!='AZ34' for e in result['entries'])


def test_no_notification_is_not_a_positive_routing_value():
    result=resolve({'incident_type':'Благодарность','city':'Москва','victims':'no'})
    assert result['matched'] and not result['services']
    assert any('Без оповещения' in e['value'] for e in result['excluded'])


def test_catalogue_revision_not_silently_downgraded():
    result=resolve({'incident_type':'БВС Регион','city':'Москва'})
    assert not result['matched'] and result['warning']


def test_other_city_requires_manual_review():
    result=resolve(fire(city='Барселона',victims='yes'))
    assert not result['matched'] and not result['services']
    assert 'другого города' in result['warning']


def test_territory_respects_tinao_and_unknown_location():
    result=resolve(fire(district='Троицкий административный округ'))
    assert any(e['cell']=='BY5' for e in result['entries'])
    assert all(e['cell']!='BX5' for e in result['entries'])
    result=resolve({'incident_type':'пожар: мусор','victims':'no'})
    assert any(e['cell']=='BY5' for e in result['unresolved'])


def test_medical_refusal_is_not_absence_from_scene():
    assert flags(fire(medical_refusal='yes'))['absent'] is False
    assert flags(fire(traits='Пострадавшие не на месте'))['absent'] is True
    assert flags(fire(victims_absent='yes'))['absent'] is True
    result=resolve(fire(medical_refusal='yes',victims='yes'))
    assert all(e['cell']!='AA5' for e in result['entries'])
