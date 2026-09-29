from typing import Literal, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator

class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)

class Question(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=4000)
    audio_id: str | None = None
    required: bool = True

class Criterion(BaseModel):
    id: str
    label: str = Field(min_length=1, max_length=300)
    kind: Literal['field','question','service','status','time','manual','contact','validation']
    field: str = ''
    expected: Any = ''
    weight: int = Field(default=10, ge=1, le=100)
    critical: bool = False
    skill: str = 'Полнота карточки'

class Contact(BaseModel):
    voice_gender: Literal["male","female"] = "male"
    voice_lines: list[dict] = Field(default_factory=list,max_length=60)
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    phone: str = Field(default='', max_length=60)
    kind: Literal['brigade','service','caller'] = 'brigade'
    service: str = Field(default='', max_length=160)
    response: str = Field(default='Информация принята.', max_length=4000)
    updates: list[str] = Field(default_factory=list, max_length=20)
    questions: list[Question] = Field(default_factory=list,max_length=30)

class Task(BaseModel):
    caller_gender: Literal['male','female'] | None = None
    scenario_details: dict[str,str] = Field(default_factory=dict)
    onboarding: Literal["112-1","112-2","dds-1","dds-2"] | None = None
    id: str
    title: str = Field(min_length=1, max_length=200)
    mode: Literal['112','dds'] = '112'
    category: str = Field(default='Происшествие', max_length=100)
    intro: str = Field(min_length=1, max_length=5000)
    intro_audio: str | None = None
    phone: str = '+7 (000) 000-00-01'
    source: str = ''
    method_note: str = 'Учебный пример. Требует предметной проверки.'
    limit_seconds: int = Field(default=30, ge=30, le=7200)
    contacts: list[Contact] = Field(default_factory=list, max_length=50)
    validation_note: str = Field(default='', max_length=4000)
    origin: Literal['author','student'] = 'author'
    own_service: str = 'ДДС района'
    questions: list[Question] = Field(default_factory=list, max_length=80)
    initial_card: dict = Field(default_factory=dict)
    expected_card: dict = Field(default_factory=dict)
    type_options: list[str] = Field(default_factory=list)
    traits: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    routing: list[dict] = Field(default_factory=list)
    service_events: list[dict] = Field(default_factory=list,max_length=100)
    @field_validator('service_events')
    @classmethod
    def validate_voice_events(cls,events):
        for event in events:
            if event.get('voice_gender','male') not in ('male','female'):raise ValueError('Выберите мужской или женский голос')
            if len(str(event.get('text','')))>5000:raise ValueError('Реплика не должна превышать 5000 символов')
            if 'spoken' in event and not isinstance(event['spoken'],bool):raise ValueError('Озвучка должна быть включена или выключена')
        return events

    criteria: list[Criterion] = Field(default_factory=list, max_length=100)

class TicketData(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=4000)
    difficulty: Literal['Базовый','Средний','Сложный'] = 'Базовый'
    difficulty_stars: int = Field(default=0, ge=0, le=5)
    difficulty_reason: str = Field(default='', max_length=500)
    tasks: list[Task] = Field(min_length=1, max_length=20)

class Command(BaseModel):
    model_config = ConfigDict(extra='forbid')
    command_id: str = Field(min_length=8, max_length=80)
    revision: int
    type: Literal['accept_call','question','ai_question','draft','notify','end_call','worklog','status','finish','hint','pause','resume','abort','contact','validate_card','accept_dds_call']
    payload: dict = Field(default_factory=dict)

class UserIn(BaseModel):
    login: str = Field(min_length=3, max_length=80, pattern=r'^[a-zA-Z0-9_.-]+$')
    name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=8, max_length=128)
    role: Literal['student','teacher','admin']
    group_id: int | None = None
    audit_access: bool = False

class AssignmentIn(BaseModel):
    version_id: int
    students: list[int] = Field(min_length=1, max_length=100)
    start_mode: Literal['self','teacher'] = 'self'
    training: bool = True

class ReviewIn(BaseModel):
    criteria: dict[str, bool]
    confirm: bool = False
    reason: str = Field(min_length=3, max_length=2000)
