"""Stable public repository API."""

from app.repositories.base import BaseRepository
from app.repositories.benchmark import (
    BenchmarkExperimentRepository,
    BenchmarkResultRepository,
    BenchmarkExampleResultRepository,
    DatasetVersionRepository,
)
from app.repositories.complaint import ComplaintRepository
from app.repositories.benchmark_comparison import BenchmarkComparisonRepository
from app.repositories.complaint_category import ComplaintCategoryRepository
from app.repositories.dataset_example import DatasetExampleRepository
from app.repositories.department import DepartmentRepository
from app.repositories.model_version import ModelVersionRepository
from app.repositories.prediction import PredictionRepository
from app.repositories.review import ReviewRepository
from app.repositories.user import UserRepository

__all__ = [
    "BaseRepository",
    "BenchmarkExperimentRepository",
    "BenchmarkResultRepository",
    "BenchmarkExampleResultRepository",
    "BenchmarkComparisonRepository",
    "ComplaintRepository",
    "ComplaintCategoryRepository",
    "DatasetExampleRepository",
    "DepartmentRepository",
    "DatasetVersionRepository",
    "ModelVersionRepository",
    "PredictionRepository",
    "ReviewRepository",
    "UserRepository",
]
