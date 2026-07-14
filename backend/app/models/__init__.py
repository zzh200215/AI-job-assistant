"""Import all ORM models so SQLAlchemy metadata is complete."""

from app.models.agent import AgentStepLog, AgentTask, RetrievalLog, SelfCheckLog
from app.models.agent_run import AgentMessage, AgentResult, AgentRun
from app.models.ai_release import AIRelease
from app.models.audit_log import AuditLog
from app.models.embedding_usage import EmbeddingUsageDaily
from app.models.history import AnalysisRecord, JobDescription, Resume, ResumeVersion
from app.models.interview_evaluation import InterviewTurnEvaluation
from app.models.interview_question import InterviewQuestion
from app.models.interview_session import InterviewSession
from app.models.job_journal import JobJournal
from app.models.job_pipeline import JobApplicationPipeline
from app.models.job_recommend import JobBookmark, JobRecommendationFeedback
from app.models.job_target import JobTarget
from app.models.knowledge import KnowledgeDocument
from app.models.notification import Notification
from app.models.operational_alert import OperationalAlert
from app.models.organization import Organization, OrganizationMembership, OrganizationSSOIdentity
from app.models.prompt_trace import PromptTrace
from app.models.subscription import SubscriptionOrder, SubscriptionPlan, UserSubscription
from app.models.user import User

__all__ = [
    "AgentMessage",
    "AgentResult",
    "AgentRun",
    "AgentStepLog",
    "AgentTask",
    "AIRelease",
    "AnalysisRecord",
    "AuditLog",
    "EmbeddingUsageDaily",
    "JobBookmark",
    "InterviewSession",
    "InterviewTurnEvaluation",
    "InterviewQuestion",
    "JobApplicationPipeline",
    "JobDescription",
    "JobJournal",
    "JobRecommendationFeedback",
    "JobTarget",
    "KnowledgeDocument",
    "Notification",
    "OperationalAlert",
    "Organization",
    "OrganizationMembership",
    "OrganizationSSOIdentity",
    "PromptTrace",
    "Resume",
    "ResumeVersion",
    "RetrievalLog",
    "SelfCheckLog",
    "SubscriptionOrder",
    "SubscriptionPlan",
    "User",
    "UserSubscription",
]
