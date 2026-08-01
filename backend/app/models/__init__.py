"""Import all ORM models so SQLAlchemy metadata is complete."""

from app.models.agent import AgentStepLog, AgentTask, RetrievalLog, SelfCheckLog
from app.models.agent_run import AgentMessage, AgentResult, AgentRun
from app.models.ai_release import AIRelease
from app.models.api_bill import ApiBill
from app.models.api_key import ApiKey
from app.models.api_pricing import ApiPricing
from app.models.api_usage import ApiUsage
from app.models.audit_log import AuditLog
from app.models.embedding_usage import EmbeddingUsageDaily
from app.models.history import AnalysisRecord, JobDescription, Resume, ResumeVersion
from app.models.interview_config import InterviewQuestionBank, InterviewReportTemplate, InterviewScoringRule
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
from app.models.organization import Organization, OrganizationMembership, OrganizationSSOIdentity, OrganizationSSOState
from app.models.prompt_trace import PromptTrace
from app.models.subscription import SubscriptionOrder, SubscriptionPlan, UserSubscription
from app.models.tenant import TenantConfig, TenantDomainBinding
from app.models.user import User
from app.models.webhook import WebhookSubscription

__all__ = [
    "AgentMessage",
    "AgentResult",
    "AgentRun",
    "AgentStepLog",
    "AgentTask",
    "AIRelease",
    "AnalysisRecord",
    "ApiBill",
    "ApiKey",
    "ApiPricing",
    "ApiUsage",
    "AuditLog",
    "EmbeddingUsageDaily",
    "JobBookmark",
    "InterviewQuestionBank",
    "InterviewReportTemplate",
    "InterviewScoringRule",
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
    "OrganizationSSOState",
    "PromptTrace",
    "Resume",
    "ResumeVersion",
    "RetrievalLog",
    "SelfCheckLog",
    "SubscriptionOrder",
    "SubscriptionPlan",
    "TenantConfig",
    "TenantDomainBinding",
    "User",
    "UserSubscription",
    "WebhookSubscription",
]
