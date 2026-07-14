from app.models.knowledge import KnowledgeDocument
from scripts.import_knowledge import exists


def _add_doc(db_session, *, status: str) -> None:
    db_session.add(
        KnowledgeDocument(
            title="data analyst skill model",
            file_name="data_analyst_skill_model.md",
            file_type="md",
            file_size=128,
            file_path="uploads/knowledge/data_analyst_skill_model.md",
            doc_type="skill_model",
            chunk_count=1 if status == "ready" else 0,
            status=status,
            error_msg=None if status == "ready" else "embedding failed",
        )
    )
    db_session.commit()


def test_import_skip_existing_only_counts_ready_documents(db_session):
    _add_doc(db_session, status="failed")

    assert not exists(
        db_session,
        title="data analyst skill model",
        file_name="data_analyst_skill_model.md",
        doc_type="skill_model",
    )

    _add_doc(db_session, status="ready")

    assert exists(
        db_session,
        title="data analyst skill model",
        file_name="data_analyst_skill_model.md",
        doc_type="skill_model",
    )
