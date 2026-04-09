import os
import sys
from pathlib import Path

TEST_DB = Path('backend/data/runtime/test_minimal.db').as_posix()
os.environ['SQLITE_PATH'] = TEST_DB
os.environ['STARTUP_INDEX_CATALOG'] = 'false'
sys.path.insert(0, str(Path('backend').resolve()))

import pytest
from fastapi.testclient import TestClient

from app.core.config import ensure_data_dirs, settings
from app.core.db import init_db
from app.main import app
from app.services.provider import provider
from app.services.storage_service import storage_service


@pytest.fixture()
def client(monkeypatch):
    ensure_data_dirs()
    db_path = settings.sqlite_path_resolved
    if db_path.exists():
        db_path.unlink()
    init_db()

    monkeypatch.setattr(provider, 'health', lambda: True)
    monkeypatch.setattr(provider, 'chat', lambda messages: 'Test reply from mocked provider.')
    monkeypatch.setattr(provider, 'stream_chat', lambda messages: iter(['Test ', 'stream ', 'reply']))
    monkeypatch.setattr(provider, 'embed', lambda texts: [None for _ in texts])

    return TestClient(app)


@pytest.fixture()
def sample_conversation(client):
    created = client.post('/api/conversations', json={'title': 'Sample Session'})
    conversation_id = created.json()['conversation']['id']
    return conversation_id


@pytest.fixture()
def uploaded_source(client, sample_conversation):
    content = (
        b'AI major has machine learning and Python labs. '
        b'CS major has algorithms and systems. '
        b'Week 5 covers machine learning lab practice. '
        b'AI Midterm Exam: 2026-05-14 at 10:00 AM.'
    )
    files = [('files', ('syllabus.txt', content, 'text/plain'))]
    response = client.post(f'/api/upload?conversation_id={sample_conversation}', files=files)
    payload = response.json()
    source_id = payload['uploaded'][0]['source_id']
    return {'conversation_id': sample_conversation, 'source_id': source_id}


@pytest.fixture()
def second_uploaded_source(client):
    created = client.post('/api/conversations', json={'title': 'Session B'})
    conversation_id = created.json()['conversation']['id']
    files = [('files', ('schedule.txt', b'Business program schedule has accounting and finance courses in year one and year two.', 'text/plain'))]
    response = client.post(f'/api/upload?conversation_id={conversation_id}', files=files)
    payload = response.json()
    source_id = payload['uploaded'][0]['source_id']
    return {'conversation_id': conversation_id, 'source_id': source_id}


@pytest.fixture()
def catalog_source(storage):
    from app.services.retrieval_service import retrieval_service

    source_id = 'catalog'
    storage.upsert_source(source_id, 'Catalog (All PDF Sources)', 'catalog', None)
    retrieval_service.index_source_text(
        source_id,
        'Sample undergraduate offerings include Artificial Intelligence, Computer Science, '
        'and Mechanical Engineering with structured study plans and catalog requirements.',
    )
    return source_id


@pytest.fixture()
def storage():
    return storage_service
