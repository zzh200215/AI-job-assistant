from app.services.scoring_config import DEFAULT_WEIGHTS, GRAD_WEIGHTS, get_weights_for_job


def test_get_weights_for_job_accepts_none_title():
    weights = get_weights_for_job(None, 3)
    assert weights == DEFAULT_WEIGHTS


def test_get_weights_for_job_accepts_invalid_experience():
    weights = get_weights_for_job(None, None)
    assert weights == GRAD_WEIGHTS
