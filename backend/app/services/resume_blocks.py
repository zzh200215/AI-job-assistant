"""Stable anchors over a parsed resume, so a rewrite can point at real text.

`Resume.parsed_json` carries no span, line number or id (see the parse prompt in
`app/prompts/resume_parse.py`), and `ResumeVersion` is a parallel Markdown
projection that nothing scores. So an "edit" written against the Markdown never
reaches the data `compute_rubric` reads. This module supplies the missing address
space: every rewritable text gets a deterministic `block_id`, and edits are
applied against that id and rejected if it does not exist.
"""

from __future__ import annotations

import copy
import re
from typing import Any

SKILLS_BLOCK_ID = "skills"
SELF_EVALUATION_BLOCK_ID = "self_evaluation"

_SKILL_SEPARATORS = re.compile(r"[、,，;；\n/|]+")
_INDEX_IN_BLOCK_ID = re.compile(r"\[(\d+)\]")


def _work_label(entry: dict[str, Any], index: int) -> str:
    company = str(entry.get("company") or "").strip()
    title = str(entry.get("title") or entry.get("position") or "").strip()
    parts = [p for p in (company, title) if p]
    return " · ".join(parts) if parts else f"工作经历 {index + 1}"


def _project_label(entry: dict[str, Any], index: int) -> str:
    name = str(entry.get("name") or "").strip()
    role = str(entry.get("role") or "").strip()
    parts = [p for p in (name, role) if p]
    return " · ".join(parts) if parts else f"项目经历 {index + 1}"


def _block(block_id: str, kind: str, label: str, text: str) -> dict[str, Any]:
    return {
        "block_id": block_id,
        "kind": kind,
        "label": label,
        "text": text,
        "char_count": len(text),
    }


def build_resume_blocks(parsed: dict[str, Any] | None) -> list[dict[str, Any]]:
    """List the texts a rewrite may legitimately target.

    Only non-empty blocks are returned: an absent section is a completeness gap,
    and offering it as a rewrite slot invites the model to invent experience the
    candidate never had.
    """
    data = parsed or {}
    blocks: list[dict[str, Any]] = []

    skills = [str(s).strip() for s in (data.get("skills") or []) if str(s).strip()]
    if skills:
        blocks.append(_block(SKILLS_BLOCK_ID, "skills", "技能清单", "、".join(skills)))

    self_eval = str(data.get("self_evaluation") or "").strip()
    if self_eval:
        blocks.append(_block(SELF_EVALUATION_BLOCK_ID, "self_evaluation", "自我评价", self_eval))

    for index, entry in enumerate(data.get("work_experience") or []):
        if not isinstance(entry, dict):
            continue
        desc = str(entry.get("desc") or "").strip()
        if desc:
            blocks.append(_block(f"work[{index}].desc", "work", _work_label(entry, index), desc))

    for index, entry in enumerate(data.get("project_experience") or []):
        if not isinstance(entry, dict):
            continue
        desc = str(entry.get("desc") or "").strip()
        if desc:
            blocks.append(_block(f"proj[{index}].desc", "project", _project_label(entry, index), desc))

    return blocks


def _split_skills(text: str) -> list[str]:
    seen: set[str] = set()
    skills: list[str] = []
    for part in _SKILL_SEPARATORS.split(text):
        item = part.strip()
        if item and item not in seen:
            seen.add(item)
            skills.append(item)
    return skills


def _entry_list(parsed: dict[str, Any], key: str) -> list[Any]:
    value = parsed.get(key)
    return value if isinstance(value, list) else []


def _resolve(parsed: dict[str, Any], block_id: str) -> tuple[str, dict[str, Any] | None, str] | None:
    """Resolve an anchor to (kind, entry, current_text), or None if unwritable.

    Resolution goes through `build_resume_blocks`, so an edit can only ever land
    on text that was advertised as rewritable. Matching the id grammar separately
    would let a suggestion create content in a section the candidate left blank.
    """
    for block in build_resume_blocks(parsed):
        if block["block_id"] != block_id:
            continue
        kind = block["kind"]
        if block_id in (SKILLS_BLOCK_ID, SELF_EVALUATION_BLOCK_ID):
            return kind, None, block["text"]

        key = "work_experience" if kind == "work" else "project_experience"
        match = _INDEX_IN_BLOCK_ID.search(block_id)
        if not match:
            return None
        entries = _entry_list(parsed, key)
        index = int(match.group(1))
        if index >= len(entries) or not isinstance(entries[index], dict):
            return None
        return kind, entries[index], block["text"]
    return None


def apply_block_edits(
    parsed: dict[str, Any] | None, edits: list[dict[str, Any]] | None
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply anchored edits, returning (new_parsed, applied, rejected).

    `new_parsed` is always a deep copy: reassigning it onto `Resume.parsed_json`
    is what marks the ORM column dirty and advances `update_time`, which is the
    resume version every score and recommendation cache keys off. Mutating in
    place would apply the edit while leaving every cached score claiming the old
    resume still matched.

    Unknown anchors are reported, never dropped silently — a hallucinated
    anchor has to be visible to the caller that asked for it.
    """
    source = parsed if isinstance(parsed, dict) else {}
    target = copy.deepcopy(source)
    applied: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for position, edit in enumerate(edits or []):
        if not isinstance(edit, dict):
            rejected.append({"index": position, "block_id": None, "reason": "not_an_object"})
            continue

        block_id = edit.get("block_id")
        if not isinstance(block_id, str) or not block_id:
            rejected.append({"index": position, "block_id": None, "reason": "missing_block_id"})
            continue

        proposed = edit.get("proposed_text")
        if not isinstance(proposed, str) or not proposed.strip():
            rejected.append({"index": position, "block_id": block_id, "reason": "empty_or_missing_text"})
            continue

        slot = _resolve(target, block_id)
        if slot is None:
            rejected.append({"index": position, "block_id": block_id, "reason": "unknown_block"})
            continue

        kind, entry, before = slot
        text = proposed.strip()

        # Anchors are positional, so a suggestion generated against an older copy
        # of the resume can point at different text by the time it is applied.
        expected = edit.get("expected_original")
        if isinstance(expected, str) and expected.strip() != before:
            rejected.append({"index": position, "block_id": block_id, "reason": "stale_anchor"})
            continue

        if kind == "skills":
            skills = _split_skills(text)
            if not skills:
                rejected.append({"index": position, "block_id": block_id, "reason": "empty_skill_list"})
                continue
            target["skills"] = skills
            after = "、".join(skills)
        elif kind == "self_evaluation":
            target["self_evaluation"] = text
            after = text
        else:
            entry["desc"] = text
            after = text

        if before == after:
            rejected.append({"index": position, "block_id": block_id, "reason": "unchanged"})
            continue

        applied.append({"index": position, "block_id": block_id, "kind": kind, "before": before, "after": after})

    return target, applied, rejected
