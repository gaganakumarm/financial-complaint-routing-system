"""Application persistence models."""

from app.db.base import Base

from app.models.benchmark_experiment import (
    BenchmarkExperiment,
    BenchmarkExperimentStatus,
)
from app.models.benchmark_comparison import BenchmarkComparison
from app.models.benchmark_comparison_member import BenchmarkComparisonMember
from app.models.benchmark_result import BenchmarkResult
from app.models.benchmark_example_result import BenchmarkExampleResult
from app.models.complaint import Complaint, ComplaintStatus, ComplaintUrgency
from app.models.complaint_category import ComplaintCategory
from app.models.complaint_status_history import (
    ComplaintChangeSource,
    ComplaintStatusHistory,
)
from app.models.department import Department
from app.models.dataset_example import DatasetExample
from app.models.dataset_version import DatasetSplit, DatasetVersion
from app.models.model_version import ModelType, ModelVersion
from app.models.model_promotion_decision import ModelPromotionDecision, ModelPromotionStatus
from app.models.deployment_candidate import DeploymentCandidate, DeploymentCandidateStatus
from app.models.prediction import Prediction
from app.models.review import Review, ReviewOutcome
from app.models.role import Role
from app.models.user import User

__all__ = [
    "Base",
    "BenchmarkExperiment",
    "BenchmarkComparison",
    "BenchmarkComparisonMember",
    "BenchmarkExperimentStatus",
    "BenchmarkResult",
    "BenchmarkExampleResult",
    "Complaint",
    "ComplaintCategory",
    "ComplaintChangeSource",
    "ComplaintStatus",
    "ComplaintStatusHistory",
    "ComplaintUrgency",
    "Department",
    "DatasetSplit",
    "DatasetExample",
    "DatasetVersion",
    "ModelType",
    "ModelVersion",
    "ModelPromotionDecision",
    "ModelPromotionStatus",
    "DeploymentCandidate",
    "DeploymentCandidateStatus",
    "Prediction",
    "Review",
    "ReviewOutcome",
    "Role",
    "User",
]
