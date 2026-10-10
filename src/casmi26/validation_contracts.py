from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Literal


ValidationProtocol = Literal[
    "library_holdout",
    "molecule_disjoint",
    "novelty_holdout",
]


@dataclass(frozen=True, slots=True)
class SplitManifest:
    """Versioned, deterministic membership contract for validation protocols."""

    protocol: ValidationProtocol
    seed: int
    dataset_fingerprint: str
    train_spectrum_ids: tuple[str, ...]
    reference_spectrum_ids: tuple[str, ...]
    validation_spectrum_ids: tuple[str, ...]
    ranker_train_identity_keys: tuple[str, ...]
    validation_identity_keys: tuple[str, ...]
    candidate_identity_keys: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for name in (
            "train_spectrum_ids",
            "reference_spectrum_ids",
            "validation_spectrum_ids",
            "ranker_train_identity_keys",
            "validation_identity_keys",
            "candidate_identity_keys",
        ):
            payload[name] = list(payload[name])
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SplitManifest:
        values = dict(payload)
        for name in (
            "train_spectrum_ids",
            "reference_spectrum_ids",
            "validation_spectrum_ids",
            "ranker_train_identity_keys",
            "validation_identity_keys",
            "candidate_identity_keys",
        ):
            values[name] = tuple(values.get(name, ()))
        return cls(**values)

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @property
    def manifest_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> SplitManifest:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class LeakageIssue:
    code: str
    message: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LeakageAuditReport:
    protocol: ValidationProtocol
    passed: bool
    issues: tuple[LeakageIssue, ...]
    checks: dict[str, int | bool]

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "passed": self.passed,
            "issues": [asdict(issue) for issue in self.issues],
            "checks": dict(self.checks),
        }


@dataclass(frozen=True, slots=True)
class RetrievalDiagnostics:
    query_count: int
    candidate_recall_at: dict[int, float]
    pool_recall: float
    mrr_at_25: float
    hit_at_1: float
    hit_at_5: float
    hit_at_10: float
    conditional_mrr_at_25: float
    oracle_mrr_at_25: float
    recovered_query_count: int
    missing_query_ids: tuple[str, ...]
    same_formula_error_count: int
    breakdowns: dict[str, dict[str, dict[str, float | int]]]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidate_recall_at"] = {
            str(key): value for key, value in sorted(self.candidate_recall_at.items())
        }
        payload["missing_query_ids"] = list(self.missing_query_ids)
        return payload
