# -*- coding: utf-8 -*-
from app.services.match_score_calibration import apply_match_score_cap, infer_match_score_cap


def test_caps_frontend_only_candidate_for_fullstack_role():
    cap = infer_match_score_cap(
        "8年前端开发负责人，精通React/Vue/TypeScript，有团队管理经验",
        "全栈开发工程师，5年+经验，要求React+Node.js+PostgreSQL",
    )

    assert cap == 55


def test_caps_senior_product_when_years_and_growth_data_tech_missing():
    cap = infer_match_score_cap(
        "2年产品经理，B端SaaS经验，熟悉需求分析/用户调研/PRD",
        "高级产品经理，3-5年B端经验，要求用户增长+数据驱动，加分项：技术背景",
    )

    assert cap == 50


def test_caps_traditional_project_manager_for_technical_pm_role():
    cap = infer_match_score_cap(
        "10年传统行业项目经理，PMP认证，熟悉项目全流程，无技术背景",
        "技术项目经理，5年+经验，要求敏捷开发+技术判断力+跨团队协作，加分项：PMP",
    )

    assert cap == 40


def test_does_not_cap_strong_backend_match():
    cap = infer_match_score_cap(
        "3年Python后端开发，熟悉FastAPI/Django/MySQL/Docker，有1个RAG项目经验",
        "Python后端开发工程师，3-5年经验，要求FastAPI+MySQL+Docker",
    )

    assert cap is None


def test_apply_match_score_cap_clamps_only_when_needed():
    result = {"match_score": 85}

    apply_match_score_cap(
        result,
        "10年传统行业项目经理，PMP认证，熟悉项目全流程，无技术背景",
        "技术项目经理，5年+经验，要求敏捷开发+技术判断力+跨团队协作，加分项：PMP",
    )

    assert result["match_score"] == 40
