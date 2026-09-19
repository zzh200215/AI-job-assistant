"""B2: one authority for "does this resume already have this skill?".

Four places answered that independently — the recommendation engine's set
difference, the match rubric's skill and bonus dimensions, the analysis report's
`missing_skills`, and the career agent's free-text `gap_skills` — with different
key fallbacks and different text handling. A candidate could be told they are
missing "K8s" by one panel and not by another.

This module owns three things and nothing else does: what a skill name means
after normalization, how a resume's or a JD's skill list is read out of
`parsed_json`, and what a gap is. Every gap carries the JD ids and the source
wording that produced it, so a displayed gap can be traced back to real postings
instead of to a model's impression.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

# Spelling variants that mean the same skill without needing context. Deliberately
# narrow: ambiguous abbreviations (TS, ML, PG) are left alone because in Chinese
# job postings they routinely mean something else (技术支持 / 机器学习 / 权限组).
_SKILL_ALIASES: dict[str, str] = {
    "js": "javascript",
    "java-script": "javascript",
    "nodejs": "node-js",
    "node-js": "node-js",
    "golang": "go",
    "k8s": "kubernetes",
    "kubernetes-cluster": "kubernetes",
    "postgres": "postgresql",
    "my-sql": "mysql",
    "oop": "object-oriented",
    "llm": "large-language-model",
    "rag": "retrieval-augmented-generation",
}

# Names whose "+" and "#" are part of the identity, not punctuation to trim.
_SPECIAL_NAMES: tuple[tuple[str, str], ...] = (
    ("c++", "c-plus-plus"),
    ("cpp", "c-plus-plus"),
    ("c#", "c-sharp"),
    ("f#", "f-sharp"),
)

_SEPARATORS = re.compile(r"[\s_./\\|-]+")
_EDGE_NOISE = re.compile(r"^[^\w\u4e00-\u9fff+#-]+|[^\w\u4e00-\u9fff+#-]+$", re.UNICODE)


def normalize_skill(value: Any) -> str:
    """Lowercase, width-fold and squeeze a name. No alias resolution.

    Use this for keyword text (JD responsibilities, project descriptions). To
    compare skills use `canonical_skill`, which additionally folds variants.
    """
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    for special, replacement in _SPECIAL_NAMES:
        text = text.replace(special, replacement)
    text = _EDGE_NOISE.sub("", text)
    text = _SEPARATORS.sub("-", text)
    return text.strip("-")


def canonical_skill(value: Any) -> str:
    """The identity used to decide whether a skill is present or missing."""
    normalized = normalize_skill(value)
    if not normalized:
        return ""
    return _SKILL_ALIASES.get(normalized, normalized)


def _skill_strings(container: Any, keys: tuple[str, ...]) -> list[str]:
    """Read the first key that has anything, in the order given.

    A fallback chain, not a union: when a posting states `required_skills`, a
    leftover `skills` key on the same record must not be promoted to a hard
    requirement.
    """
    if not isinstance(container, dict):
        return []
    out: list[str] = []
    for key in keys:
        raw = container.get(key)
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, dict):
                for name_key in ("skill", "name", "requirement"):
                    value = item.get(name_key)
                    if isinstance(value, (str, int, float)) and str(value).strip():
                        out.append(str(value))
                        break
            elif isinstance(item, (str, int, float)) and str(item).strip():
                out.append(str(item))
        if out:
            break
    return out


def skill_field(container: Any, key: str) -> list[str]:
    """Read one skill-bearing list field (e.g. a project's `tech`) by name."""
    return _skill_strings(container, (key,))


def resume_skill_names(parsed: Any) -> list[str]:
    return _skill_strings(parsed, ("skills",))


def jd_required_names(parsed: Any) -> list[str]:
    """Required skills. `skills` is the fallback for imported postings that never
    got a required/nice split — the old code read it *instead of* required_skills,
    which silently dropped half of a JD's requirements."""
    return _skill_strings(parsed, ("required_skills", "skills"))


def jd_nice_to_have_names(parsed: Any) -> list[str]:
    return _skill_strings(parsed, ("nice_to_have",))


def skill_spellings(names: list[str]) -> dict[str, list[str]]:
    """canonical name -> the exact strings that produced it, in input order.

    This is the trace: a gap says "kubernetes", and the evidence says the posting
    wrote "K8s".
    """
    seen: dict[str, list[str]] = {}
    for name in names:
        key = canonical_skill(name)
        if not key:
            continue
        spellings = seen.setdefault(key, [])
        if name not in spellings:
            spellings.append(name)
    return seen


@dataclass
class SkillGap:
    """One resume measured against one job posting, with its evidence."""

    jd_id: int | None = None
    title: str = ""
    matched_required: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    matched_nice_to_have: list[str] = field(default_factory=list)
    missing_nice_to_have: list[str] = field(default_factory=list)
    required_total: int = 0
    nice_total: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def coverage(self) -> float | None:
        """Share of required skills present. None when the JD named none: that is
        unknown, not 0%, and must not be scored as either."""
        if not self.required_total:
            return None
        return len(self.matched_required) / self.required_total

    def to_dict(self) -> dict[str, Any]:
        return {
            "jd_id": self.jd_id,
            "title": self.title,
            "matched_required": list(self.matched_required),
            "missing_required": list(self.missing_required),
            "matched_nice_to_have": list(self.matched_nice_to_have),
            "missing_nice_to_have": list(self.missing_nice_to_have),
            "required_total": self.required_total,
            "nice_total": self.nice_total,
            "coverage": None if self.coverage is None else round(self.coverage, 4),
            "evidence": self.evidence,
        }


def build_skill_gap(
    resume_parsed: Any,
    jd_parsed: Any,
    *,
    jd_id: int | None = None,
    title: str = "",
    fallback_required: list[str] | None = None,
) -> SkillGap:
    """`fallback_required` is used only when the parsed JSON states no required
    skills — e.g. `JobDescription.skill_tags` on a record parsed before the split
    existed. Same rule the match rubric applies, so the two cannot disagree about
    what a posting asks for."""
    resume_map = skill_spellings(resume_skill_names(resume_parsed))
    required_names = jd_required_names(jd_parsed) or [str(s) for s in (fallback_required or [])]
    required_map = skill_spellings(required_names)
    nice_map = skill_spellings(jd_nice_to_have_names(jd_parsed))

    present = set(resume_map)
    required = set(required_map)
    nice = set(nice_map) - required

    return SkillGap(
        jd_id=jd_id,
        title=title,
        matched_required=sorted(required & present),
        missing_required=sorted(required - present),
        matched_nice_to_have=sorted(nice & present),
        missing_nice_to_have=sorted(nice - present),
        required_total=len(required),
        nice_total=len(nice),
        evidence={"resume": resume_map, "required": required_map, "nice_to_have": nice_map},
    )


def jd_skill_union(parsed: Any, fallback_required: list[str] | None = None) -> list[str]:
    """Everything a posting asks for, required and nice-to-have together."""
    required = jd_required_names(parsed) or [str(s) for s in (fallback_required or [])]
    return required + jd_nice_to_have_names(parsed)


def aggregate_skill_gaps(gaps: list[SkillGap], *, limit: int = 12) -> list[dict[str, Any]]:
    """Rank gaps across many postings so a plan can cite the market.

    Each entry names the postings that demand the skill — "6 of the 11 backend
    JDs ask for Redis" instead of "Redis is popular".
    """
    per_skill: dict[str, dict[str, Any]] = {}

    def row_for(skill: str) -> dict[str, Any]:
        return per_skill.setdefault(skill, {"skill": skill, "required_by": set(), "nice_for": set()})

    for gap in gaps:
        for skill in gap.missing_required:
            row = row_for(skill)
            row["weight"] = row.get("weight", 0.0) + 2.0
            if gap.jd_id is not None:
                row["required_by"].add(gap.jd_id)
        for skill in gap.missing_nice_to_have:
            row = row_for(skill)
            row["weight"] = row.get("weight", 0.0) + 1.0
            if gap.jd_id is not None:
                row["nice_for"].add(gap.jd_id)

    ranked = sorted(per_skill.values(), key=lambda row: (-row.get("weight", 0.0), row["skill"]))
    return [
        {
            "skill": row["skill"],
            "required_by_jd_ids": sorted(row["required_by"]),
            "nice_for_jd_ids": sorted(row["nice_for"]),
            "required_count": len(row["required_by"]),
            "nice_count": len(row["nice_for"]),
            "priority": "高" if row["required_by"] else "中",
        }
        for row in ranked[:limit]
    ]
