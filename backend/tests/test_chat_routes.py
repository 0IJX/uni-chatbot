import io

import pandas as pd


def _build_exam_schedule_xlsx() -> bytes:
    frame = pd.DataFrame(
        [
            {
                "Course Code": "CSE 104",
                "Course Name": "Introduction to Computing",
                "Exam Date": "2026-05-20",
                "Exam Time": "10:00 AM",
                "Location": "Room A101",
                "Week": "Week 8",
                "Notes": "Midterm",
            },
            {
                "Course Code": "MAT 113",
                "Course Name": "Calculus I",
                "Exam Date": "2026-05-20",
                "Exam Time": "1:00 PM",
                "Location": "Room B204",
                "Week": "Week 8",
                "Notes": "Final",
            },
        ]
    )
    handle = io.BytesIO()
    with pd.ExcelWriter(handle, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Exam Schedule")
    return handle.getvalue()


def test_conversation_crud(client):
    created = client.post('/api/conversations', json={'title': 'Session A'})
    assert created.status_code == 200
    conversation_id = created.json()['conversation']['id']

    listed = client.get('/api/conversations')
    assert listed.status_code == 200
    rows = listed.json()['conversations']
    assert any(row['id'] == conversation_id for row in rows)

    deleted = client.delete(f'/api/conversations?conversation_id={conversation_id}')
    assert deleted.status_code == 200

    listed_after = client.get('/api/conversations')
    rows_after = listed_after.json()['conversations']
    assert not any(row['id'] == conversation_id for row in rows_after)


def test_upload_and_retrieval_success(client, uploaded_source):
    response = client.post(
        '/api/chat',
        json={
            'conversation_id': uploaded_source['conversation_id'],
            'source_id': uploaded_source['source_id'],
            'message': 'summarize ai major content',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['source_id'] == uploaded_source['source_id']
    assert payload['citations'], 'Expected retrieval citations for matching query.'


def test_uploaded_file_summarization_uses_selected_source(client, uploaded_source):
    response = client.post(
        '/api/chat',
        json={
            'conversation_id': uploaded_source['conversation_id'],
            'source_id': uploaded_source['source_id'],
            'message': 'summarize this uploaded file',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['source_id'] == uploaded_source['source_id']
    assert payload['citations']


def test_upload_creates_document_sections(client, storage):
    created = client.post('/api/conversations', json={'title': 'Section Build Session'})
    conversation_id = created.json()['conversation']['id']
    content = (
        'Program Overview\n'
        'Artificial Intelligence prepares students for machine learning work.\n\n'
        'Admission Requirements\n'
        'Applicants must complete MAT 113 and maintain a GPA of 2.5.\n\n'
        'Semester Schedule\n'
        'Semester 1 includes CSE 104 and LNG 101.'
    )
    files = [('files', ('structured.txt', content.encode('utf-8'), 'text/plain'))]
    upload = client.post(f'/api/upload?conversation_id={conversation_id}', files=files)
    assert upload.status_code == 200
    source_id = upload.json()['uploaded'][0]['source_id']

    sections = storage.get_sections(source_id)
    assert len(sections) >= 2
    assert any('Requirements' in item['section_title'] for item in sections)
    assert all(isinstance(item.get('chunk_ids', []), list) for item in sections)


def test_retrieval_failure_returns_grounded_no_evidence(client, uploaded_source):
    response = client.post(
        '/api/chat',
        json={
            'conversation_id': uploaded_source['conversation_id'],
            'source_id': uploaded_source['source_id'],
            'message': 'compare astroSCIics and marine law requirements',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['citations'] == []
    assert 'couldn\'t find relevant evidence' in payload['reply'].lower()


def test_schedule_query_hits_schedule_section(client):
    created = client.post('/api/conversations', json={'title': 'Schedule Session'})
    conversation_id = created.json()['conversation']['id']
    file_content = (
        'Admission Requirements\n'
        'Students must submit transcript and passport copy.\n\n'
        'Semester Schedule\n'
        'Semester 1: CSE 104, MAT 113\n'
        'Semester 2: CSE 112, SCI 110\n'
    )
    files = [('files', ('schedule.txt', file_content.encode('utf-8'), 'text/plain'))]
    upload = client.post(f'/api/upload?conversation_id={conversation_id}', files=files)
    source_id = upload.json()['uploaded'][0]['source_id']

    response = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'source_id': source_id,
            'message': 'what is the semester schedule',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['citations']
    assert any('Semester Schedule' in item['preview'] for item in payload['citations'])


def test_personal_schedule_query_prefers_uploaded_source(client, uploaded_source, catalog_source):
    response = client.post(
        '/api/chat',
        json={
            'conversation_id': uploaded_source['conversation_id'],
            'source_id': uploaded_source['source_id'],
            'message': 'what do I have this week in my schedule',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['source_id'] == uploaded_source['source_id']
    assert payload['citations']
    assert payload['citations'][0]['source_id'] == uploaded_source['source_id']


def test_catalog_question_can_override_selected_upload_source(client, uploaded_source, catalog_source):
    response = client.post(
        '/api/chat',
        json={
            'conversation_id': uploaded_source['conversation_id'],
            'source_id': uploaded_source['source_id'],
            'message': 'what majors does catalog offer',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['source_id'] == catalog_source
    assert payload['citations']
    assert any(item['source_id'] == catalog_source for item in payload['citations'])


def test_mixed_question_uses_upload_and_catalog_context(client, catalog_source):
    created = client.post('/api/conversations', json={'title': 'Mixed Source Session'})
    conversation_id = created.json()['conversation']['id']
    mixed_file = (
        'My Syllabus Weekly Plan\n'
        'Week 3 focuses on machine learning lab and project checkpoint.\n'
        'Exam date for AI midterm is Week 8 Tuesday.'
    )
    files = [('files', ('my_schedule.txt', mixed_file.encode('utf-8'), 'text/plain'))]
    upload = client.post(f'/api/upload?conversation_id={conversation_id}', files=files)
    source_id = upload.json()['uploaded'][0]['source_id']

    response = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'source_id': source_id,
            'message': 'using my syllabus and catalog, compare requirements with my current week',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['citations']
    citation_sources = {item['source_id'] for item in payload['citations']}
    assert source_id in citation_sources
    assert catalog_source in citation_sources


def test_ambiguous_follow_up_keeps_source_context(client, uploaded_source):
    conversation_id = uploaded_source['conversation_id']
    source_id = uploaded_source['source_id']

    first = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'source_id': source_id,
            'message': 'tell me about the ai major',
        },
    )
    assert first.status_code == 200

    follow_up = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'message': 'major?',
        },
    )
    assert follow_up.status_code == 200
    payload = follow_up.json()
    assert payload['source_id'] == source_id
    assert payload['citations']


def test_catalog_specific_question_defaults_to_catalog_source(client, catalog_source):
    created = client.post('/api/conversations', json={'title': 'Catalog Session'})
    conversation_id = created.json()['conversation']['id']

    response = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'message': 'catalog offerings',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['source_id'] == catalog_source
    assert payload['citations']


def test_cross_source_switching_uses_requested_source(client, uploaded_source, second_uploaded_source):
    conversation_id = uploaded_source['conversation_id']
    source_a = uploaded_source['source_id']
    source_b = second_uploaded_source['source_id']

    first = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'source_id': source_a,
            'message': 'tell me about ai major',
        },
    )
    assert first.status_code == 200
    assert first.json()['source_id'] == source_a

    switched = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'source_id': source_b,
            'message': 'business schedule courses',
        },
    )
    assert switched.status_code == 200
    payload = switched.json()
    assert payload['source_id'] == source_b
    assert payload['citations']
    assert all(item['source_id'] == source_b for item in payload['citations'])


def test_compare_prompt_with_partial_evidence(client):
    created = client.post('/api/conversations', json={'title': 'Compare Session'})
    conversation_id = created.json()['conversation']['id']

    files = [('files', ('ai_only.txt', b'Artificial intelligence major emphasizes machine learning projects.', 'text/plain'))]
    upload = client.post(f'/api/upload?conversation_id={conversation_id}', files=files)
    source_id = upload.json()['uploaded'][0]['source_id']

    response = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'source_id': source_id,
            'message': 'compare artificial intelligence with computer science',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['citations']
    assert 'couldn\'t find relevant evidence' not in payload['reply'].lower()


def test_study_plan_prompt_with_weak_evidence_returns_no_evidence(client):
    created = client.post('/api/conversations', json={'title': 'Weak Study Plan Session'})
    conversation_id = created.json()['conversation']['id']

    files = [('files', ('policy.txt', b'This file describes attendance policy and code of conduct only.', 'text/plain'))]
    upload = client.post(f'/api/upload?conversation_id={conversation_id}', files=files)
    source_id = upload.json()['uploaded'][0]['source_id']

    response = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'source_id': source_id,
            'message': 'create me a study plan',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['citations'] == []
    assert 'couldn\'t find relevant evidence' in payload['reply'].lower()
    assert 'general study approach' in payload['reply'].lower()


def test_exam_question_from_uploaded_file(client):
    created = client.post('/api/conversations', json={'title': 'Exam Session'})
    conversation_id = created.json()['conversation']['id']
    file_content = (
        'Course Exam Schedule\n'
        'AI Midterm Exam: 2026-05-14\n'
        'Final Exam: 2026-06-20'
    )
    files = [('files', ('exam_schedule.txt', file_content.encode('utf-8'), 'text/plain'))]
    upload = client.post(f'/api/upload?conversation_id={conversation_id}', files=files)
    source_id = upload.json()['uploaded'][0]['source_id']

    response = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'source_id': source_id,
            'message': 'when is the exam for ai',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['source_id'] == source_id
    assert payload['citations']


def test_google_sheet_exam_schedule_questions_retrieve_rows(client, monkeypatch):
    xlsx_payload = _build_exam_schedule_xlsx()

    class FakeResponse:
        def __init__(self, status_code=200, headers=None, content=b""):
            self.status_code = status_code
            self.headers = headers or {}
            self.content = content
            self.text = content.decode('utf-8', errors='ignore')

    def fake_get(url, *args, **kwargs):
        if 'docs.google.com/spreadsheets' in url and 'format=xlsx' in url:
            return FakeResponse(
                status_code=200,
                headers={"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                content=xlsx_payload,
            )
        return FakeResponse(status_code=404, headers={"content-type": "text/plain"}, content=b'not found')

    monkeypatch.setattr("app.services.ingest_service.requests.get", fake_get)

    created = client.post('/api/conversations', json={'title': 'Google Sheet Exam Session'})
    conversation_id = created.json()['conversation']['id']

    ingest = client.post(
        '/api/upload-url',
        json={
            'conversation_id': conversation_id,
            'url': 'https://docs.google.com/spreadsheets/d/googleExamSheet123/edit#gid=0',
        },
    )
    assert ingest.status_code == 200
    source_id = ingest.json()['uploaded'][0]['source_id']

    queries = [
        'when is the exam for CSE 104',
        'where is the final for MAT 113',
        'what exams do I have this week',
        'do I have two exams on the same day',
    ]

    for query in queries:
        response = client.post(
            '/api/chat',
            json={
                'conversation_id': conversation_id,
                'source_id': source_id,
                'message': query,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload['source_id'] == source_id
        assert payload['citations']


def test_google_sheet_no_match_returns_honest_no_evidence(client, monkeypatch):
    xlsx_payload = _build_exam_schedule_xlsx()

    class FakeResponse:
        def __init__(self, content):
            self.status_code = 200
            self.headers = {"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
            self.content = content
            self.text = ""

    monkeypatch.setattr("app.services.ingest_service.requests.get", lambda *args, **kwargs: FakeResponse(xlsx_payload))

    created = client.post('/api/conversations', json={'title': 'Google No Match'})
    conversation_id = created.json()['conversation']['id']
    ingest = client.post(
        '/api/upload-url',
        json={
            'conversation_id': conversation_id,
            'url': 'https://docs.google.com/spreadsheets/d/googleExamSheet123/edit#gid=0',
        },
    )
    source_id = ingest.json()['uploaded'][0]['source_id']

    response = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'source_id': source_id,
            'message': 'tell me about marine biology coral reefs',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['citations'] == []
    assert payload['reply']


def test_google_sheet_follow_up_keeps_source_context(client, monkeypatch):
    xlsx_payload = _build_exam_schedule_xlsx()

    class FakeResponse:
        def __init__(self, content):
            self.status_code = 200
            self.headers = {"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
            self.content = content
            self.text = ""

    monkeypatch.setattr("app.services.ingest_service.requests.get", lambda *args, **kwargs: FakeResponse(xlsx_payload))

    created = client.post('/api/conversations', json={'title': 'Google Follow-up'})
    conversation_id = created.json()['conversation']['id']
    ingest = client.post(
        '/api/upload-url',
        json={
            'conversation_id': conversation_id,
            'url': 'https://docs.google.com/spreadsheets/d/googleExamSheet123/edit#gid=0',
        },
    )
    source_id = ingest.json()['uploaded'][0]['source_id']

    first = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'source_id': source_id,
            'message': 'when is the exam for CSE 104',
        },
    )
    assert first.status_code == 200
    assert first.json()['citations']

    follow_up = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'message': 'and where is it',
        },
    )
    assert follow_up.status_code == 200
    payload = follow_up.json()
    assert payload['source_id'] == source_id
    assert payload['citations']


def test_chat_stream_happy_path(client, uploaded_source):
    with client.stream(
        'POST',
        '/api/chat/stream',
        json={
            'conversation_id': uploaded_source['conversation_id'],
            'source_id': uploaded_source['source_id'],
            'message': 'hello there',
        },
    ) as response:
        assert response.status_code == 200
        body = ''.join(response.iter_text())
        assert 'event: meta' in body
        assert 'event: token' in body
        assert 'event: done' in body


def test_provider_failure_fallback_chat(client, uploaded_source, monkeypatch):
    from app.services.provider import provider

    def _fail_chat(_messages):
        raise RuntimeError('provider down')

    monkeypatch.setattr(provider, 'chat', _fail_chat)

    response = client.post(
        '/api/chat',
        json={
            'conversation_id': uploaded_source['conversation_id'],
            'source_id': uploaded_source['source_id'],
            'message': 'tell me about ai major',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['reply']
    assert 'couldn\'t reach ollama' not in payload['reply'].lower()


def test_provider_failure_fallback_stream(client, uploaded_source, monkeypatch):
    from app.services.provider import provider

    def _fail_stream(_messages):
        raise RuntimeError('stream provider down')

    monkeypatch.setattr(provider, 'stream_chat', _fail_stream)

    with client.stream(
        'POST',
        '/api/chat/stream',
        json={
            'conversation_id': uploaded_source['conversation_id'],
            'source_id': uploaded_source['source_id'],
            'message': 'summarize this uploaded file',
        },
    ) as response:
        assert response.status_code == 200
        body = ''.join(response.iter_text())
        assert 'event: done' in body


def test_message_persistence_after_chat(client, uploaded_source):
    conversation_id = uploaded_source['conversation_id']
    source_id = uploaded_source['source_id']

    response = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'source_id': source_id,
            'message': 'what can you do',
        },
    )
    assert response.status_code == 200

    conversation_data = client.get(f'/api/conversations?conversation_id={conversation_id}')
    assert conversation_data.status_code == 200
    payload = conversation_data.json()
    messages = payload['messages']

    assert len(messages) >= 2
    assert messages[-2]['role'] == 'user'
    assert messages[-1]['role'] == 'assistant'


def test_upload_invalid_type_rejected(client):
    files = [('files', ('archive.zip', b'PK...', 'application/zip'))]
    response = client.post('/api/upload', files=files)
    assert response.status_code == 400


def test_follow_up_persists_comparison_context(client, uploaded_source, storage):
    conversation_id = uploaded_source['conversation_id']
    source_id = uploaded_source['source_id']

    first = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'source_id': source_id,
            'message': 'compare artificial intelligence with computer science',
        },
    )
    assert first.status_code == 200
    first_state = storage.get_conversation_state(conversation_id)
    assert first_state['active_compare_pair'] == ['Artificial Intelligence', 'Computer Science']

    follow_up = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'message': 'and the second one',
        },
    )
    assert follow_up.status_code == 200
    payload = follow_up.json()
    assert payload['source_id'] == source_id
    assert payload['citations']

    second_state = storage.get_conversation_state(conversation_id)
    assert second_state['active_entity'] == 'Computer Science'


def test_partial_exact_location_question_hedges_cleanly(client):
    created = client.post('/api/conversations', json={'title': 'Location Hedge Session'})
    conversation_id = created.json()['conversation']['id']
    file_content = (
        'Course Exam Schedule\n'
        'CSE 104 Midterm Exam: 2026-05-14 at 10:00 AM\n'
        'Bring your student ID card.'
    )
    files = [('files', ('exam_info.txt', file_content.encode('utf-8'), 'text/plain'))]
    upload = client.post(f'/api/upload?conversation_id={conversation_id}', files=files)
    source_id = upload.json()['uploaded'][0]['source_id']

    response = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'source_id': source_id,
            'message': 'where is the exam for CSE 104',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['citations']
    assert "can't fully verify the location" in payload['reply'].lower()


def test_mixed_source_exact_conflict_is_called_out(client, storage):
    from app.services.retrieval_service import retrieval_service

    storage.upsert_source('catalog', 'Catalog (All PDF Sources)', 'catalog', None)
    retrieval_service.index_source_document(
        source_id='catalog',
        transcript='Official AI exam notice. CSE 104 Midterm Exam: 2026-05-16 at 10:00 AM.',
        sections=[
            {
                'section_title': 'Official Exam Schedule',
                'section_type': 'schedule',
                'section_text': 'Official AI exam notice. CSE 104 Midterm Exam: 2026-05-16 at 10:00 AM.',
                'keywords': ['exam', 'schedule', 'CSE 104'],
                'page_start': 18,
                'page_end': 18,
                'facts': {
                    'dates': ['2026-05-16'],
                    'times': ['10:00 AM'],
                    'locations': [],
                    'weeks': [],
                    'course_codes': ['CSE 104'],
                },
            }
        ],
    )

    created = client.post('/api/conversations', json={'title': 'Conflict Session'})
    conversation_id = created.json()['conversation']['id']
    upload_text = 'My syllabus says CSE 104 Midterm Exam: 2026-05-14 at 10:00 AM.'
    upload = client.post(
        f'/api/upload?conversation_id={conversation_id}',
        files=[('files', ('my_exam.txt', upload_text.encode('utf-8'), 'text/plain'))],
    )
    source_id = upload.json()['uploaded'][0]['source_id']

    response = client.post(
        '/api/chat',
        json={
            'conversation_id': conversation_id,
            'source_id': source_id,
            'message': 'based on my syllabus and the catalog, when is the exam for CSE 104',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    citation_sources = {item['source_id'] for item in payload['citations']}
    assert source_id in citation_sources
    assert 'catalog' in citation_sources
    assert 'conflicting exam date details' in payload['reply'].lower()


def test_live_external_requests_are_limited_honestly(client):
    response = client.post(
        '/api/chat',
        json={
            'message': 'what is the weather today in city x',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['citations'] == []
    assert "can't verify live external facts" in payload['reply'].lower()
