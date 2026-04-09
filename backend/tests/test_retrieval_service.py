from app.services.retrieval_service import retrieval_service
from app.services.storage_service import storage_service


def test_section_first_retrieval_targets_requirements():
    source_id = "src_test_section_target"
    storage_service.upsert_source(source_id, "catalog.txt", "upload", None)
    retrieval_service.index_source_document(
        source_id=source_id,
        transcript="Program and requirements transcript",
        sections=[
            {
                "section_title": "Program Overview",
                "section_type": "program",
                "section_text": "Artificial Intelligence program focuses on machine learning and automation.",
                "keywords": ["artificial intelligence", "program"],
                "page_start": 2,
                "page_end": 3,
            },
            {
                "section_title": "Admission Requirements",
                "section_type": "requirements",
                "section_text": "Applicants must complete MATematics prerequisites and maintain a minimum GPA of 2.5.",
                "keywords": ["requirements", "admission", "gpa"],
                "page_start": 10,
                "page_end": 11,
            },
            {
                "section_title": "Study Plan",
                "section_type": "schedule",
                "section_text": "Semester one includes CSE 101 and MAT 113. Semester two includes CSE 112 and SCI 110.",
                "keywords": ["semester", "study plan"],
                "page_start": 20,
                "page_end": 21,
            },
        ],
    )

    matches = retrieval_service.search(source_id, "what are the reqs for admission", top_k=4)
    assert matches
    top = matches[0]
    assert top["section_title"] == "Admission Requirements"
    assert top["section_type"] == "requirements"
    assert top["page_start"] == 10


def test_query_expansion_handles_ai_cs_and_studyplan():
    source_id = "src_test_query_expansion"
    storage_service.upsert_source(source_id, "study_plan.txt", "upload", None)
    retrieval_service.index_source_document(
        source_id=source_id,
        transcript="Study plan transcript",
        sections=[
            {
                "section_title": "Bachelor of Science in Artificial Intelligence Study Plan",
                "section_type": "courses",
                "section_text": "Semester one: CSE 104, MAT 113. Semester two: CSE 112, SCI 110.",
                "keywords": ["artificial intelligence", "study plan", "semester"],
                "page_start": 5,
                "page_end": 7,
            },
            {
                "section_title": "Computer Science Program",
                "section_type": "program",
                "section_text": "Computer Science emphasizes algorithms, operating systems, and software engineering.",
                "keywords": ["computer science", "algorithms"],
                "page_start": 8,
                "page_end": 9,
            },
        ],
    )

    ai_plan = retrieval_service.search(source_id, "ai studyplan", top_k=3)
    assert ai_plan
    assert "Artificial Intelligence" in (ai_plan[0]["section_title"] or "")

    cs_program = retrieval_service.search(source_id, "cs program focus", top_k=3)
    assert cs_program
    assert "Computer Science" in (cs_program[0]["section_title"] or "")


def test_retrieval_no_match_returns_empty():
    source_id = "src_test_retrieval_nomatch"
    storage_service.upsert_source(source_id, "retrieval.txt", "upload", None)
    retrieval_service.index_source_text(
        source_id,
        "Artificial Intelligence includes machine learning and neural networks. "
        "Computer science includes algorithms and systems.",
    )

    failure = retrieval_service.search(source_id, "marine biology coral reefs", top_k=3)
    assert failure == []
