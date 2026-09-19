"""B1.2: line-level rewrite suggestions, bounded to text the candidate wrote.

The model receives only the anchored blocks `build_resume_blocks` advertises and
must answer per anchor. Every returned suggestion is re-checked here, because a
suggestion that slips past validation becomes a fabricated line in someone's
CV: unknown anchors, paraphrased "originals", no-op rewrites and rewrites that
invent new achievements are all rejected and reported.

Nothing here persists. Suggestions live in the response, so a degraded or mocked
model answer cannot outlive the request that produced it.
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.history import JobDescription, Resume, ResumeVersion
from app.prompts.rendering import render_prompt
from app.prompts.resume_rewrite import RESUME_REWRITE_PROMPT
from app.services.llm_service import chat_json, set_llm_trace_context
from app.services.match_score_service import canonical_match_score, resume_version_of
from app.services.resume_blocks import apply_block_edits, build_resume_blocks
from app.utils.service_access import get_accessible_job_for_user, get_owned_resume

logger = logging.getLogger(__name__)

MAX_SUGGESTIONS = 8


def _length_ceiling(original: str) -> int:
    """A rewrite may clarify, not inflate. Short lines get absolute slack so a
    one-line self evaluation can still gain a clause."""
    return max(len(original) * 2, len(original) + 120)


def _prompt_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"block_id": b["block_id"], "label": b["label"], "text": b["text"]} for b in blocks]


def validate_rewrite_suggestions(
    blocks: list[dict[str, Any]], payload: Any, limit: int = MAX_SUGGESTIONS
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a model response into usable suggestions and refusals.

    Pure function so the gate can be tested without a model in the loop.
    """
    by_id = {block["block_id"]: block for block in blocks}
    raw = payload.get("suggestions") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        return [], [{"block_id": None, "reason": "malformed_response"}]

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in raw:
        if not isinstance(item, dict):
            rejected.append({"block_id": None, "reason": "not_an_object"})
            continue

        block_id = item.get("block_id")
        block = by_id.get(block_id) if isinstance(block_id, str) else None
        if block is None:
            rejected.append({"block_id": block_id if isinstance(block_id, str) else None, "reason": "unknown_block"})
            continue

        if block_id in seen:
            rejected.append({"block_id": block_id, "reason": "duplicate_block"})
            continue

        original = item.get("original")
        if not isinstance(original, str) or original.strip() != block["text"]:
            rejected.append({"block_id": block_id, "reason": "original_mismatch"})
            continue

        proposed = item.get("proposed_text")
        if not isinstance(proposed, str) or not proposed.strip():
            rejected.append({"block_id": block_id, "reason": "empty_proposal"})
            continue
        if proposed.strip() == block["text"]:
            rejected.append({"block_id": block_id, "reason": "unchanged"})
            continue
        if len(proposed.strip()) > _length_ceiling(block["text"]):
            rejected.append({"block_id": block_id, "reason": "proposal_too_long"})
            continue

        seen.add(block_id)
        accepted.append(
            {
                "block_id": block_id,
                "kind": block["kind"],
                "label": block["label"],
                "original": block["text"],
                "proposed_text": proposed.strip(),
                "reason": str(item.get("reason") or "").strip(),
            }
        )

    if len(accepted) > limit:
        for extra in accepted[limit:]:
            rejected.append({"block_id": extra["block_id"], "reason": "over_limit"})
        accepted = accepted[:limit]

    return accepted, rejected


def build_rewrite_suggestions(
    db: Session,
    resume_id: int,
    jd_id: int | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Return anchored 原文 → 改后 suggestions for one resume."""
    resume: Resume | None = (
        get_owned_resume(db, resume_id, user_id) if user_id is not None else db.get(Resume, resume_id)
    )
    if not resume:
        raise ValueError("简历不存在或无权限")

    blocks = build_resume_blocks(resume.parsed_json)
    if not blocks:
        return {
            "resume_id": resume_id,
            "jd_id": jd_id,
            "block_total": 0,
            "suggestions": [],
            "rejected": [],
            "note": "这份简历里没有可供改写的文本块，需要先补全内容",
        }

    jd: JobDescription | None = None
    if jd_id is not None:
        jd = (
            get_accessible_job_for_user(db, jd_id, user_id) if user_id is not None else db.get(JobDescription, jd_id)
        )
        if not jd:
            raise ValueError("目标岗位不存在或无权限")
    jd_text = (
        json.dumps(jd.parsed_json or {"title": jd.title}, ensure_ascii=False)
        if jd
        else "未指定目标岗位，按通用简历质量改写。"
    )

    set_llm_trace_context(
        {
            "source": "resume_rewrite_service.build_rewrite_suggestions",
            "prompt_version": "resume-rewrite-v1",
            "resume_id": resume_id,
            "jd_id": jd_id,
            "user_id": user_id,
        }
    )
    prompt = render_prompt(
        RESUME_REWRITE_PROMPT,
        blocks_json=json.dumps(_prompt_blocks(blocks), ensure_ascii=False, indent=2),
        jd_text=jd_text,
        max_suggestions=MAX_SUGGESTIONS,
    )
    result = chat_json(prompt)

    suggestions, rejected = validate_rewrite_suggestions(blocks, result)
    return {
        "resume_id": resume_id,
        "jd_id": jd_id,
        "block_total": len(blocks),
        "suggestions": suggestions,
        "rejected": rejected,
    }


def _load_pair(db: Session, resume_id: int, jd_id: int | None, user_id: int | None) -> tuple[Resume, JobDescription | None]:
    resume: Resume | None = (
        get_owned_resume(db, resume_id, user_id) if user_id is not None else db.get(Resume, resume_id)
    )
    if not resume:
        raise ValueError("简历不存在或无权限")
    jd: JobDescription | None = None
    if jd_id is not None:
        jd = (
            get_accessible_job_for_user(db, jd_id, user_id) if user_id is not None else db.get(JobDescription, jd_id)
        )
        if not jd:
            raise ValueError("目标岗位不存在或无权限")
    return resume, jd


def _score_view(score: dict[str, Any] | None) -> dict[str, Any] | None:
    if not score:
        return None
    return {"score": score.get("score"), "raw_score": score.get("raw_score"), "method": score.get("method")}


def apply_rewrite_suggestions(
    db: Session,
    resume_id: int,
    edits: list[dict[str, Any]] | None,
    jd_id: int | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Write accepted edits back onto the resume and re-score the target job.

    The pre-edit `parsed_json` is kept as a JSON version row: applying a rewrite
    overwrites the only copy of the candidate's wording, so without that
    snapshot "撤销" would be impossible and the change would be irreversible by
    accident.
    """
    resume, jd = _load_pair(db, resume_id, jd_id, user_id)
    old_parsed = copy.deepcopy(resume.parsed_json or {})
    before_score = _score_view(canonical_match_score(db, resume, jd, user_id=user_id)) if jd else None

    new_parsed, applied, rejected = apply_block_edits(old_parsed, edits)
    if not applied:
        return {
            "resume_id": resume_id,
            "changed": False,
            "applied": [],
            "rejected": rejected,
            "resume_version": resume_version_of(resume),
            "score": {"before": before_score, "after": before_score, "delta": None},
        }

    snapshot = ResumeVersion(
        resume_id=resume.id,
        version_type="manual",
        content=json.dumps(old_parsed, ensure_ascii=False),
        format="json",
        label="行级改写前快照",
        target_jd_id=jd_id,
        change_log=applied,
    )
    db.add(snapshot)
    # Reassigning (not mutating) is what marks the JSON column dirty; see
    # tests/test_resume_version_identity.py for what happens otherwise.
    resume.parsed_json = new_parsed
    db.add(resume)
    db.commit()
    db.refresh(resume)

    after_score = _score_view(canonical_match_score(db, resume, jd, user_id=user_id)) if jd else None
    delta = (
        round(after_score["score"] - before_score["score"], 2)
        if after_score and before_score and after_score["score"] is not None and before_score["score"] is not None
        else None
    )

    return {
        "resume_id": resume_id,
        "changed": True,
        "applied": applied,
        "rejected": rejected,
        "snapshot_version_id": snapshot.id,
        "resume_version": resume_version_of(resume),
        "block_total": len(build_resume_blocks(resume.parsed_json)),
        "score": {"before": before_score, "after": after_score, "delta": delta},
    }
