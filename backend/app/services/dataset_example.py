"""Validation and persistence orchestration for dataset examples."""

from dataclasses import dataclass
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.models import ComplaintUrgency, DatasetExample
from app.repositories import ComplaintCategoryRepository, DatasetExampleRepository, DatasetVersionRepository, DepartmentRepository


class DatasetExampleServiceError(Exception): pass
class DatasetExampleNotFoundError(DatasetExampleServiceError): pass
class DatasetExampleAlreadyExistsError(DatasetExampleServiceError): pass
class InvalidDatasetExampleError(DatasetExampleServiceError): pass
class DatasetExampleReferenceError(DatasetExampleServiceError): pass
class DatasetVersionNotFoundForExampleError(DatasetExampleServiceError): pass
class DatasetExamplePersistenceError(DatasetExampleServiceError): pass


@dataclass(frozen=True, slots=True)
class DatasetExampleInput:
    example_id: str
    title: str
    description: str
    expected_category_id: UUID
    expected_department_id: UUID
    expected_urgency: ComplaintUrgency


class DatasetExampleService:
    def __init__(self, *, dataset_version_repository: DatasetVersionRepository, dataset_example_repository: DatasetExampleRepository, complaint_category_repository: ComplaintCategoryRepository, department_repository: DepartmentRepository) -> None:
        self._dataset_version_repository = dataset_version_repository
        self._dataset_example_repository = dataset_example_repository
        self._complaint_category_repository = complaint_category_repository
        self._department_repository = department_repository

    async def _dataset(self, dataset_version_id: UUID):
        if not isinstance(dataset_version_id, UUID):
            raise InvalidDatasetExampleError("Dataset example data is invalid.")
        dataset = await self._dataset_version_repository.get_by_id(dataset_version_id)
        if dataset is None:
            raise DatasetVersionNotFoundForExampleError("Dataset version was not found.")
        return dataset

    async def create_examples(self, *, dataset_version_id: UUID, examples: Sequence[DatasetExampleInput]) -> list[DatasetExample]:
        await self._dataset(dataset_version_id)
        if isinstance(examples, (str, bytes)) or not isinstance(examples, Sequence) or not 1 <= len(examples) <= 500:
            raise InvalidDatasetExampleError("Dataset example data is invalid.")
        validated: list[DatasetExampleInput] = []
        ids: set[str] = set()
        for item in examples:
            if not isinstance(item, DatasetExampleInput) or not isinstance(item.expected_category_id, UUID) or not isinstance(item.expected_department_id, UUID) or not isinstance(item.expected_urgency, ComplaintUrgency):
                raise InvalidDatasetExampleError("Dataset example data is invalid.")
            example_id, title, description = item.example_id.strip(), item.title.strip(), item.description.strip()
            if not example_id or len(example_id) > 200 or example_id in ids or not title or len(title) > 200 or not description or len(description) > 10_000:
                raise InvalidDatasetExampleError("Dataset example data is invalid.")
            ids.add(example_id)
            validated.append(DatasetExampleInput(example_id, title, description, item.expected_category_id, item.expected_department_id, item.expected_urgency))
        categories = await self._complaint_category_repository.get_by_ids({item.expected_category_id for item in validated})
        departments = await self._department_repository.get_by_ids({item.expected_department_id for item in validated})
        if any((category := categories.get(item.expected_category_id)) is None or not category.is_active for item in validated):
            raise DatasetExampleReferenceError("Dataset example reference is invalid.")
        if any((department := departments.get(item.expected_department_id)) is None or not department.is_active for item in validated):
            raise DatasetExampleReferenceError("Dataset example reference is invalid.")
        if await self._dataset_example_repository.example_ids_exist(dataset_version_id=dataset_version_id, example_ids=ids):
            raise DatasetExampleAlreadyExistsError("Dataset example already exists.")
        rows = [DatasetExample(dataset_version_id=dataset_version_id, example_id=item.example_id, title=item.title, description=item.description, expected_category_id=item.expected_category_id, expected_department_id=item.expected_department_id, expected_urgency=item.expected_urgency) for item in validated]
        try:
            for row in rows:
                await self._dataset_example_repository.add(row)
            await self._dataset_example_repository.flush()
            return [await self._dataset_example_repository.refresh(row) for row in rows]
        except IntegrityError as exc:
            raise DatasetExampleAlreadyExistsError("Dataset example already exists.") from None
        except Exception:
            raise DatasetExamplePersistenceError("Dataset example persistence failed.") from None

    async def list_examples(self, *, dataset_version_id: UUID, offset: int = 0, limit: int = 100) -> list[DatasetExample]:
        await self._dataset(dataset_version_id)
        return await self._dataset_example_repository.list_for_dataset(dataset_version_id, offset=offset, limit=limit)

    async def get_example(self, *, dataset_version_id: UUID, example_id: str) -> DatasetExample:
        await self._dataset(dataset_version_id)
        row = await self._dataset_example_repository.get_for_dataset_and_example_id(dataset_version_id=dataset_version_id, example_id=example_id)
        if row is None:
            raise DatasetExampleNotFoundError("Dataset example was not found.")
        return row


__all__ = ["DatasetExampleInput", "DatasetExampleService", "DatasetExampleServiceError", "DatasetExampleNotFoundError", "DatasetExampleAlreadyExistsError", "DatasetExamplePersistenceError", "InvalidDatasetExampleError", "DatasetExampleReferenceError", "DatasetVersionNotFoundForExampleError"]
