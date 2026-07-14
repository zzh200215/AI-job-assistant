"""Per-user recommendation tuning config storage and validation."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Any

_CONFIG_LOCK = Lock()
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "reports" / "recommendation_tuning_configs.json"


DEFAULT_RECOMMENDATION_TUNING_CONFIG: dict[str, Any] = {
    "vector_weight": 0.6,
    "rule_weight": 0.4,
    "rule_components": {
        "skill": 0.5,
        "experience": 0.2,
        "salary": 0.15,
        "location": 0.15,
    },
    "thresholds": {
        "high": 80,
        "medium": 60,
    },
}

_FLOAT_MIN = 0.0
_FLOAT_MAX = 1.0


def _clamp(value: float, minimum: float = _FLOAT_MIN, maximum: float = _FLOAT_MAX) -> float:
    return max(minimum, min(maximum, value))


def _normalize_rule_components(rule_components: dict[str, float]) -> dict[str, float]:
    total = sum(float(value) for value in rule_components.values())
    if total <= 0:
        return deepcopy(DEFAULT_RECOMMENDATION_TUNING_CONFIG["rule_components"])
    normalized = {key: round(float(value) / total, 4) for key, value in rule_components.items()}
    diff = round(1.0 - sum(normalized.values()), 4)
    if abs(diff) >= 0.0001:
        first_key = next(iter(normalized))
        normalized[first_key] = round(_clamp(normalized[first_key] + diff), 4)
    return normalized


def _ensure_parent() -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _read_all() -> dict[str, Any]:
    _ensure_parent()
    if not _CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_all(payload: dict[str, Any]) -> None:
    _ensure_parent()
    _CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _float_value(payload: dict[str, Any], key: str, *, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        value = float(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {key}") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{key} out of range")
    return value


def _int_value(payload: dict[str, Any], key: str, *, minimum: int = 0, maximum: int = 100) -> int:
    try:
        value = int(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {key}") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{key} out of range")
    return value


def validate_recommendation_tuning_config(config: dict[str, Any]) -> dict[str, Any]:
    vector_weight = _float_value(config, "vector_weight")
    rule_weight = _float_value(config, "rule_weight")
    if abs((vector_weight + rule_weight) - 1.0) > 0.001:
        raise ValueError("vector_weight + rule_weight must equal 1.0")

    rule_components_raw = config.get("rule_components")
    if not isinstance(rule_components_raw, dict):
        raise ValueError("rule_components must be an object")
    rule_components = {
        "skill": _float_value(rule_components_raw, "skill"),
        "experience": _float_value(rule_components_raw, "experience"),
        "salary": _float_value(rule_components_raw, "salary"),
        "location": _float_value(rule_components_raw, "location"),
    }
    if abs(sum(rule_components.values()) - 1.0) > 0.001:
        raise ValueError("rule_components must sum to 1.0")

    thresholds_raw = config.get("thresholds")
    if not isinstance(thresholds_raw, dict):
        raise ValueError("thresholds must be an object")
    thresholds = {
        "high": _int_value(thresholds_raw, "high"),
        "medium": _int_value(thresholds_raw, "medium"),
    }
    if thresholds["high"] <= thresholds["medium"]:
        raise ValueError("threshold high must be greater than medium")

    return {
        "vector_weight": round(vector_weight, 4),
        "rule_weight": round(rule_weight, 4),
        "rule_components": {key: round(value, 4) for key, value in rule_components.items()},
        "thresholds": thresholds,
    }


def get_recommendation_tuning_config(user_id: int) -> dict[str, Any]:
    with _CONFIG_LOCK:
        payload = _read_all()
        user_config = payload.get(str(user_id))
    if not isinstance(user_config, dict):
        return deepcopy(DEFAULT_RECOMMENDATION_TUNING_CONFIG)
    try:
        return validate_recommendation_tuning_config(user_config)
    except ValueError:
        return deepcopy(DEFAULT_RECOMMENDATION_TUNING_CONFIG)


def save_recommendation_tuning_config(user_id: int, config: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_recommendation_tuning_config(config)
    with _CONFIG_LOCK:
        payload = _read_all()
        payload[str(user_id)] = normalized
        _write_all(payload)
    return normalized


def reset_recommendation_tuning_config(user_id: int) -> dict[str, Any]:
    with _CONFIG_LOCK:
        payload = _read_all()
        payload.pop(str(user_id), None)
        _write_all(payload)
    return deepcopy(DEFAULT_RECOMMENDATION_TUNING_CONFIG)


def build_feedback_tuning_recommendation(
    feedback_analysis: dict[str, Any],
    tuning_samples: list[dict[str, Any]],
    current_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive a small, explainable tuning suggestion from feedback signals."""
    current = validate_recommendation_tuning_config(current_config or DEFAULT_RECOMMENDATION_TUNING_CONFIG)
    suggested = deepcopy(current)

    total = int(feedback_analysis.get("total") or 0)
    like_rate = float(feedback_analysis.get("like_rate") or 0.0)
    dislike_rate = float(feedback_analysis.get("dislike_rate") or 0.0)
    tuning_signals = feedback_analysis.get("tuning_signals") or {}
    high_score_dislikes = tuning_signals.get("high_score_dislikes") or []
    low_score_likes = tuning_signals.get("low_score_likes") or []

    tag_counts: dict[str, int] = {}
    for item in tuning_samples:
        for tag in item.get("tuning_tags") or []:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    reasons: list[str] = []
    actions: list[dict[str, Any]] = []

    if total == 0:
        return {
            "current_config": current,
            "suggested_config": current,
            "delta": {"vector_weight": 0, "rule_weight": 0, "rule_components": {}, "thresholds": {}},
            "reasons": ["暂无反馈样本，先积累样本再调参"],
            "action_items": [],
            "sample_total": 0,
            "confidence": 0.0,
        }

    if dislike_rate >= 0.4 or len(high_score_dislikes) > len(low_score_likes):
        suggested["vector_weight"] = round(_clamp(suggested["vector_weight"] - 0.05, 0.2, 0.8), 4)
        suggested["rule_weight"] = round(1.0 - suggested["vector_weight"], 4)
        suggested["rule_components"]["skill"] = round(_clamp(suggested["rule_components"]["skill"] + 0.03), 4)
        suggested["rule_components"]["experience"] = round(_clamp(suggested["rule_components"]["experience"] + 0.01), 4)
        reasons.append("高分点踩偏多，建议降低向量通道权重并提高规则约束")
        actions.append(
            {
                "type": "reduce_vector_weight",
                "detail": "减少过高相似度对最终排序的影响，优先保留规则一致的结果。",
            }
        )

    if len(low_score_likes) >= 1 or like_rate >= 0.4:
        suggested["vector_weight"] = round(_clamp(suggested["vector_weight"] + 0.03, 0.2, 0.8), 4)
        suggested["rule_weight"] = round(1.0 - suggested["vector_weight"], 4)
        suggested["thresholds"]["medium"] = max(int(suggested["thresholds"]["medium"]) - 3, 50)
        reasons.append("低分点赞出现，建议放宽中低分阈值并略增召回倾向")
        actions.append(
            {
                "type": "lower_threshold",
                "detail": "降低中档阈值，避免把用户实际喜欢的岗位过早压到低推荐层。",
            }
        )

    if tag_counts.get("salary_gap", 0) >= 2:
        suggested["rule_components"]["salary"] = round(_clamp(suggested["rule_components"]["salary"] + 0.04), 4)
        reasons.append("薪资不匹配样本偏多，建议提高薪资匹配权重")
    if tag_counts.get("location_gap", 0) >= 2:
        suggested["rule_components"]["location"] = round(_clamp(suggested["rule_components"]["location"] + 0.04), 4)
        reasons.append("地点不匹配样本偏多，建议提高地点匹配权重")
    if tag_counts.get("experience_gap", 0) >= 2:
        suggested["rule_components"]["experience"] = round(_clamp(suggested["rule_components"]["experience"] + 0.04), 4)
        reasons.append("经验不匹配样本偏多，建议提高经验匹配权重")
    if tag_counts.get("skill_gap_heavy", 0) >= 2:
        suggested["rule_components"]["skill"] = round(_clamp(suggested["rule_components"]["skill"] + 0.05), 4)
        reasons.append("技能缺口较大样本偏多，建议提高技能匹配权重")

    suggested["rule_components"] = _normalize_rule_components(suggested["rule_components"])
    suggested = validate_recommendation_tuning_config(suggested)

    delta = {
        "vector_weight": round(suggested["vector_weight"] - current["vector_weight"], 4),
        "rule_weight": round(suggested["rule_weight"] - current["rule_weight"], 4),
        "rule_components": {
            key: round(suggested["rule_components"][key] - current["rule_components"][key], 4)
            for key in current["rule_components"]
        },
        "thresholds": {
            key: int(suggested["thresholds"][key]) - int(current["thresholds"][key]) for key in current["thresholds"]
        },
    }

    confidence = round(
        min(1.0, 0.35 + min(total, 50) / 100.0 + min(len(tag_counts), 4) * 0.08),
        3,
    )
    return {
        "current_config": current,
        "suggested_config": suggested,
        "delta": delta,
        "reasons": reasons or ["反馈样本不足以触发明确调参，建议继续积累样本"],
        "action_items": actions,
        "sample_total": total,
        "confidence": confidence,
        "signal_summary": {
            "like_rate": round(like_rate, 4),
            "dislike_rate": round(dislike_rate, 4),
            "high_score_dislike_count": len(high_score_dislikes),
            "low_score_like_count": len(low_score_likes),
            "tag_counts": tag_counts,
        },
    }
