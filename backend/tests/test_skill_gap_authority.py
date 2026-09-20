"""B2.1: one definition of "this resume already has that skill".

The engine, the match rubric, the analysis report and the career agent each
compared skill names their own way, so "K8s" and "Kubernetes" counted as a gap in
one panel and a match in another, and a JD whose parsed JSON happened to carry a
`skills` key had its `required_skills` ignored outright.
"""

from __future__ import annotations

from app.services.skill_gap import (
    aggregate_skill_gaps,
    build_skill_gap,
    canonical_skill,
    jd_nice_to_have_names,
    jd_required_names,
    normalize_skill,
    resume_skill_names,
    skill_spellings,
)

# ---------------------------------------------------------------- naming


def test_special_characters_in_skill_names_survive_normalization():
    assert normalize_skill("C++") == "c-plus-plus"
    assert normalize_skill("c++ ") == "c-plus-plus"
    assert normalize_skill("C#") == "c-sharp"
    assert normalize_skill("Python。") == "python"
    assert normalize_skill("  后端开发  ") == "后端开发"


def test_full_width_and_separators_fold_together():
    assert normalize_skill("Ｐｙｔｈｏｎ") == "python"
    assert normalize_skill("Machine Learning") == "machine-learning"
    assert normalize_skill("machine_learning") == "machine-learning"
    assert normalize_skill("RESTful/API") == "restful-api"


def test_aliases_only_cover_unambiguous_variants():
    assert canonical_skill("K8s") == "kubernetes"
    assert canonical_skill("golang") == "go"
    assert canonical_skill("Node JS") == "node-js"
    assert canonical_skill("nodejs") == "node-js"
    assert canonical_skill("JS") == "javascript"
    # TS / ML / PG are ambiguous in Chinese postings (技术支持 etc.) and must stay
    # exactly what they were written as.
    assert canonical_skill("TS") == "ts"
    assert canonical_skill("ML") == "ml"
    assert canonical_skill("PG") == "pg"


def test_chinese_and_english_names_are_not_merged():
    """No translation is happening here, so 容器编排 and kubernetes stay apart."""
    assert canonical_skill("Kubernetes") != canonical_skill("容器编排")


# ---------------------------------------------------------------- reading


def test_resume_skills_are_read_from_the_skills_key_only():
    parsed = {"skills": ["Python", {"skill": "Redis"}, {"name": "Kafka"}, "  ", 42]}
    assert resume_skill_names(parsed) == ["Python", "Redis", "Kafka", "42"]
    assert resume_skill_names({"required_skills": ["Python"]}) == []
    assert resume_skill_names(None) == []
    assert resume_skill_names({"skills": "Python"}) == ["Python"]


def test_jd_reads_required_first_and_falls_back_to_skills():
    both = {"required_skills": ["Python"], "skills": ["Legacy"], "nice_to_have": ["Redis"]}
    assert jd_required_names(both) == ["Python"]
    assert jd_required_names({"skills": ["Legacy"]}) == ["Legacy"]
    assert jd_nice_to_have_names(both) == ["Redis"]


def test_spellings_are_kept_as_the_trace():
    mapping = skill_spellings(["K8s", "Kubernetes", "k8s"])
    assert set(mapping["kubernetes"]) == {"K8s", "Kubernetes", "k8s"}


# ---------------------------------------------------------------- one gap


def _gap(resume_skills, jd_parsed, **kwargs):
    return build_skill_gap({"skills": resume_skills}, jd_parsed, **kwargs)


def test_gap_splits_required_and_nice_to_have():
    gap = _gap(
        ["Python", "K8s"],
        {"required_skills": ["Python", "MySQL"], "nice_to_have": ["Redis", "Kubernetes"]},
        jd_id=7,
        title="后端工程师",
    )

    assert gap.matched_required == ["python"]
    assert gap.missing_required == ["mysql"]
    assert gap.matched_nice_to_have == ["kubernetes"]
    assert gap.missing_nice_to_have == ["redis"]
    assert gap.coverage == 0.5
    assert gap.evidence["required"]["mysql"] == ["MySQL"]
    assert gap.evidence["nice_to_have"]["kubernetes"] == ["Kubernetes"]


def test_a_nice_to_have_already_required_is_not_counted_twice():
    gap = _gap(["Python"], {"required_skills": ["Python"], "nice_to_have": ["Python"]})

    assert gap.nice_total == 0
    assert gap.missing_nice_to_have == []
    assert gap.matched_required == ["python"]


def test_no_requirements_is_unknown_not_zero():
    gap = _gap(["Python"], {"description": "没有列出技能"})

    assert gap.required_total == 0
    assert gap.coverage is None
    assert gap.to_dict()["coverage"] is None


def test_fallback_required_covers_the_skill_tags_column():
    gap = _gap(["Python"], {}, fallback_required=["Redis"])

    assert gap.missing_required == ["redis"]
    assert gap.evidence["required"]["redis"] == ["Redis"]


def test_fallback_is_ignored_when_the_posting_states_requirements():
    """A column-level tag list must not dilute an explicit requirement set."""
    gap = _gap(["Python"], {"required_skills": ["MySQL"]}, fallback_required=["Redis"])

    assert gap.missing_required == ["mysql"]


def test_gap_matches_across_spelling_variants():
    gap = _gap(["Kubernetes", "Node.js"], {"required_skills": ["K8s", "nodejs"]})

    assert gap.missing_required == []
    assert sorted(gap.matched_required) == ["kubernetes", "node-js"]


# ---------------------------------------------------------------- aggregate


def test_aggregation_ranks_required_demand_above_nice_to_have():
    gaps = [
        _gap(["Python"], {"required_skills": ["Redis"], "nice_to_have": ["GraphQL"]}, jd_id=1),
        _gap(["Python"], {"required_skills": ["Redis"]}, jd_id=2),
        _gap(["Python"], {"nice_to_have": ["Redis"]}, jd_id=3),
    ]

    ranked = aggregate_skill_gaps(gaps)

    assert ranked[0]["skill"] == "redis"
    assert ranked[0]["required_by_jd_ids"] == [1, 2]
    assert ranked[0]["nice_for_jd_ids"] == [3]
    assert ranked[0]["priority"] == "高"
    assert ranked[1]["skill"] == "graphql"
    assert ranked[1]["priority"] == "中"
    assert ranked[1]["required_by_jd_ids"] == []


def test_aggregation_honours_the_limit():
    gaps = [_gap([], {"required_skills": [f"s{i}"]}, jd_id=i) for i in range(1, 20)]

    assert len(aggregate_skill_gaps(gaps, limit=5)) == 5
    assert aggregate_skill_gaps([]) == []


# ---------------------------------------------------------------- agreement


def test_the_rubric_and_the_gap_graph_report_the_same_missing_skills():
    """The point of one authority: two panels must not disagree about a gap."""
    from app.services.match_explainer_service import MatchExplainer

    resume_parsed = {"skills": ["Python", "K8s"], "years_exp": 3}
    jd_parsed = {"title": "后端", "required_skills": ["Python", "Kubernetes", "Redis"], "nice_to_have": ["GraphQL"]}

    _, _, skill_match = MatchExplainer()._calc_skill(resume_parsed, jd_parsed)
    graph = build_skill_gap(resume_parsed, jd_parsed)

    assert skill_match["missing_required"] == graph.missing_required == ["redis"]
    assert sorted(skill_match["matched"]) == sorted(graph.matched_required + graph.matched_nice_to_have)


def test_a_posting_with_both_keys_does_not_drop_its_requirements():
    """The engine used to read `data.get("skills", data.get("required_skills", ...))`,
    so a record carrying both had `required_skills` ignored entirely."""
    from app.services.match_explainer_service import MatchExplainer

    resume_parsed = {"name": "张三", "skills": ["Python"], "years_exp": 3}
    jd_parsed = {"title": "后端工程师", "required_skills": ["Redis"], "skills": ["Kafka"], "nice_to_have": []}

    _, _, skill_match = MatchExplainer()._calc_skill(resume_parsed, jd_parsed)
    graph = build_skill_gap(resume_parsed, jd_parsed, jd_id=5)

    assert graph.missing_required == ["redis"]
    assert graph.matched_required == []
    assert graph.missing_required == sorted(skill_match["missing_required"])
