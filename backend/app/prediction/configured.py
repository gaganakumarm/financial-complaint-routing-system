"""Deterministic predictor driven by a model version's JSON configuration."""

from math import isfinite
from numbers import Real
from uuid import UUID

from app.models import Complaint, ComplaintUrgency, ModelVersion
from app.prediction.base import PredictionOutput


class PredictorConfigurationError(Exception):
    """Raised when configured-baseline settings are invalid."""


_INVALID_CONFIGURATION = "Predictor configuration is invalid."


def _uuid(value: object) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        raise PredictorConfigurationError(_INVALID_CONFIGURATION) from None


def _urgency(value: object) -> ComplaintUrgency:
    try:
        return ComplaintUrgency(value)
    except (TypeError, ValueError):
        raise PredictorConfigurationError(_INVALID_CONFIGURATION) from None


def _confidence(value: object) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise PredictorConfigurationError(_INVALID_CONFIGURATION)
    return float(value)


def _output(values: dict, *, raw_output: dict) -> PredictionOutput:
    try:
        return PredictionOutput(
            category_id=_uuid(values["category_id"]),
            department_id=_uuid(values["department_id"]),
            urgency=_urgency(values["urgency"]),
            confidence_score=_confidence(values["confidence_score"]),
            raw_output=raw_output,
        )
    except KeyError:
        raise PredictorConfigurationError(_INVALID_CONFIGURATION) from None


class ConfiguredBaselinePredictor:
    """Apply the first matching keyword rule, otherwise configured defaults."""

    async def predict(
        self,
        *,
        complaint: Complaint,
        model_version: ModelVersion,
    ) -> PredictionOutput:
        configuration = model_version.configuration
        if not isinstance(configuration, dict):
            raise PredictorConfigurationError(_INVALID_CONFIGURATION)

        try:
            defaults = {
                "category_id": configuration["default_category_id"],
                "department_id": configuration["default_department_id"],
                "urgency": configuration["default_urgency"],
                "confidence_score": configuration["default_confidence_score"],
            }
            rules = configuration.get("keyword_rules", [])
        except KeyError:
            raise PredictorConfigurationError(_INVALID_CONFIGURATION) from None
        if not isinstance(rules, list):
            raise PredictorConfigurationError(_INVALID_CONFIGURATION)

        # Validate defaults even when a rule matches.
        _output(defaults, raw_output={"predictor": "configured_baseline"})
        text = f"{complaint.title} {complaint.description}".casefold()
        parsed_rules: list[tuple[int, list[str], PredictionOutput]] = []
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                raise PredictorConfigurationError(_INVALID_CONFIGURATION)
            keywords = rule.get("keywords")
            if (
                not isinstance(keywords, list)
                or not keywords
                or any(not isinstance(word, str) or not word.strip() for word in keywords)
            ):
                raise PredictorConfigurationError(_INVALID_CONFIGURATION)
            normalized = [word.strip().casefold() for word in keywords]
            matched = [word for word in normalized if word in text]
            values = {
                "category_id": rule.get("category_id"),
                "department_id": rule.get("department_id"),
                "urgency": rule.get("urgency"),
                "confidence_score": rule.get("confidence_score"),
            }
            # Validate every configured rule, independent of whether it matches.
            output = _output(
                values,
                raw_output={
                    "predictor": "configured_baseline",
                    "matched_rule_index": index,
                    "matched_keywords": matched,
                },
            )
            parsed_rules.append((index, matched, output))

        for _, matched, output in parsed_rules:
            if matched:
                return output

        return _output(
            defaults,
            raw_output={
                "predictor": "configured_baseline",
                "matched_rule_index": None,
                "matched_keywords": [],
            },
        )
