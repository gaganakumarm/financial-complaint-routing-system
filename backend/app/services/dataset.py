"""Transaction-neutral dataset-version metadata management."""

import json
from uuid import UUID

from app.models import DatasetSplit, DatasetVersion
from app.repositories import DatasetVersionRepository


class DatasetServiceError(Exception):
    pass


class DatasetVersionAlreadyExistsError(DatasetServiceError):
    pass


class DatasetVersionNotFoundError(DatasetServiceError):
    pass


class InvalidDatasetVersionError(DatasetServiceError):
    pass


_INVALID = "Dataset version data is invalid."


def _text(value: object, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise InvalidDatasetVersionError(_INVALID)
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise InvalidDatasetVersionError(_INVALID)
    return normalized


class DatasetService:
    def __init__(self, repository: DatasetVersionRepository) -> None:
        self._repository = repository

    async def create_dataset_version(
        self,
        *,
        name: str,
        version: str,
        source_name: str,
        source_reference: str | None,
        taxonomy_version: str,
        split: DatasetSplit,
        record_count: int,
        content_hash: str,
        preparation_details: dict | None,
    ) -> DatasetVersion:
        normalized_name = _text(name, maximum=100)
        normalized_version = _text(version, maximum=50)
        normalized_source = _text(source_name, maximum=200)
        normalized_taxonomy = _text(taxonomy_version, maximum=50)
        normalized_hash = _text(content_hash, maximum=128)
        if not isinstance(split, DatasetSplit):
            raise InvalidDatasetVersionError(_INVALID)
        if isinstance(record_count, bool) or not isinstance(record_count, int) or record_count <= 0:
            raise InvalidDatasetVersionError(_INVALID)
        if source_reference is not None and not isinstance(source_reference, str):
            raise InvalidDatasetVersionError(_INVALID)
        normalized_reference = source_reference.strip() if source_reference else None
        if preparation_details is not None:
            if not isinstance(preparation_details, dict):
                raise InvalidDatasetVersionError(_INVALID)
            try:
                json.dumps(preparation_details, allow_nan=False)
            except (TypeError, ValueError):
                raise InvalidDatasetVersionError(_INVALID) from None
        if await self._repository.get_by_identity(
            name=normalized_name, version=normalized_version, split=split
        ) is not None or await self._repository.get_by_content_hash(normalized_hash) is not None:
            raise DatasetVersionAlreadyExistsError("Dataset version already exists.")
        dataset = DatasetVersion(
            name=normalized_name,
            version=normalized_version,
            source_name=normalized_source,
            source_reference=normalized_reference,
            taxonomy_version=normalized_taxonomy,
            split=split,
            record_count=record_count,
            content_hash=normalized_hash,
            preparation_details=preparation_details,
        )
        await self._repository.add(dataset)
        await self._repository.flush()
        return await self._repository.refresh(dataset)

    async def get_dataset_version(self, dataset_version_id: UUID) -> DatasetVersion:
        dataset = await self._repository.get_by_id(dataset_version_id)
        if dataset is None:
            raise DatasetVersionNotFoundError("Dataset version was not found.")
        return dataset

    async def list_dataset_versions(
        self, *, offset: int = 0, limit: int = 100
    ) -> list[DatasetVersion]:
        return await self._repository.list(offset=offset, limit=limit)


__all__ = [
    "DatasetService",
    "DatasetServiceError",
    "DatasetVersionAlreadyExistsError",
    "DatasetVersionNotFoundError",
    "InvalidDatasetVersionError",
]
