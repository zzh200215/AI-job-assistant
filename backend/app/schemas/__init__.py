# -*- coding: utf-8 -*-
"""Pydantic Schemas"""
from app.schemas.resume import ResumeUploadResp, ResumeParseResp
from app.schemas.jd import JDCreateReq, JDCreateResp, JDParseResp
from app.schemas.analysis import MatchReq

__all__ = [
    "ResumeUploadResp",
    "ResumeParseResp",
    "JDCreateReq",
    "JDCreateResp",
    "JDParseResp",
    "MatchReq",
]
