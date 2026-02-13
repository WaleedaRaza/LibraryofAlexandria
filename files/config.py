"""Load and validate config.yaml into typed objects."""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class LLMConfig:
    provider: str = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "llama3.1:8b"
    temperature: float = 0.3
    request_timeout: int = 600


@dataclass
class ExtractionConfig:
    min_quality_threshold: float = 0.3
    ocr_detection_threshold: float = 0.5


@dataclass
class CleaningConfig:
    header_repeat_threshold: float = 0.5
    page_number_proximity: int = 20


@dataclass
class BoundariesConfig:
    chunk_size_tokens: int = 4000
    chunk_overlap_tokens: int = 500
    regex_min_sections: int = 5
    regex_min_coverage: float = 0.8


@dataclass
class EnrichmentConfig:
    max_themes_per_section: int = 7
    max_passages_per_section: int = 3


@dataclass
class ValidationConfig:
    min_confidence: float = 0.7
    max_gap_chars: int = 100


@dataclass
class BatchConfig:
    concurrency: int = 1
    checkpoint_every: int = 1
    retry_on_failure: int = 2


@dataclass
class Pipeline1Config:
    pdf_dir: str = "./data/pdfs"
    artifact_dir: str = "./data/artifacts"
    checkpoint_dir: str = "./data/checkpoints"
    flagged_dir: str = "./data/flagged"
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    cleaning: CleaningConfig = field(default_factory=CleaningConfig)
    boundaries: BoundariesConfig = field(default_factory=BoundariesConfig)
    enrichment: EnrichmentConfig = field(default_factory=EnrichmentConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    batch: BatchConfig = field(default_factory=BatchConfig)


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    pipeline1: Pipeline1Config = field(default_factory=Pipeline1Config)


def _dict_to_dataclass(cls, data: dict):
    """Recursively convert nested dicts to dataclass instances."""
    if not isinstance(data, dict):
        return data
    kwargs = {}
    for k, v in data.items():
        if k not in cls.__dataclass_fields__:
            continue
        ft = cls.__dataclass_fields__[k].type
        if isinstance(ft, str):
            ft = eval(ft)
        if hasattr(ft, "__dataclass_fields__") and isinstance(v, dict):
            kwargs[k] = _dict_to_dataclass(ft, v)
        else:
            kwargs[k] = v
    return cls(**kwargs)


def load_config(path: str | Path = "config.yaml") -> Config:
    """Load config from YAML file."""
    path = Path(path)
    if not path.exists():
        return Config()

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not raw:
        return Config()

    return _dict_to_dataclass(Config, raw)
