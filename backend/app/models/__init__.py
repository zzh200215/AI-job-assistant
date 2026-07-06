
"""Import all ORM models so SQLAlchemy metadata is complete."""

from app.models.agent import AgentStepLog, AgentTask, RetrievalLog, SelfCheckLog
from app.models.agent_run import AgentMessage, AgentResult, AgentRun
from app.models.candidate_screening import CandidateScreeningSession
from app.models.embedding_usage import EmbeddingUsageDaily
from app.models.history import AnalysisRecord, JobDescription, Resume, ResumeVersion
from app.models.interview_session import InterviewSession
from app.models.job_data_source import JobDataSource, JobImportBatch, JobSyncLog
from app.models.job_pipeline import JobApplicationPipeline
from app.models.job_recommend import JobRecommendationFeedback
from app.models.knowledge import KnowledgeDocument
from app.models.prompt_trace import PromptTrace
from app.models.user import User

__all__ = [
    "AgentMessage",
    "AgentResult",
    "AgentRun",
    "AgentStepLog",
    "AgentTask",
    "AnalysisRecord",
    "CandidateScreeningSession",
    "EmbeddingUsageDaily",
    "InterviewSession",
    "JobApplicationPipeline",
    "JobDataSource",
    "JobDescription",
    "JobImportBatch",
    "JobRecommendationFeedback",
    "JobSyncLog",
    "KnowledgeDocument",
    "PromptTrace",
    "Resume",
    "ResumeVersion",
    "RetrievalLog",
    "SelfCheckLog",
    "User",
]
