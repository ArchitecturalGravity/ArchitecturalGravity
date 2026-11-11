"""Normalized facts shared by the scored extraction responsibilities."""
from dataclasses import dataclass

SESSION_RECORD = "openai.codex_cli:session-record"
EXTRACTION_VERSION = "4.0.0"
SOURCE = "Codex CLI persisted rollout JSONL"
TOKEN_FIELDS = {"input_tokens": "input_tokens", "cached_input_tokens": "cached_input_tokens",
                "output_tokens": "output_tokens", "reasoning_tokens": "reasoning_output_tokens",
                "total_tokens": "total_tokens"}
RULES = {role: "Final token_count.info.total_token_usage." + field for role, field in TOKEN_FIELDS.items()}
RULES.update(cached_input_tokens_subset_of_input_tokens="true", reasoning_tokens_subset_of_output_tokens="true")


@dataclass(frozen=True)
class RetainedSession:
    record: dict
    records: tuple
    line_numbers: tuple
    source: str
    raw: bytes | None
    thread_id: str | None
    extraction_version: str
    runtime_version: str
    source_complete: bool


@dataclass(frozen=True)
class TokenFacts:
    tokens: dict
    cache_write_input_tokens: int | None
    context_windows: tuple
    token_events: int
    has_usage: bool
    snapshots: dict
    source_complete: bool
    authority: str = "token_count.info.total_token_usage"
    completed_responses: tuple = ()
    contradictions: tuple = ()


@dataclass(frozen=True)
class ToolFacts:
    events: tuple
    actual_tools: dict
    durations: dict
    complete: bool


@dataclass(frozen=True)
class TimingFacts:
    model: str
    effort: str
    timestamps: tuple
    prompts: tuple
    prompt_times: tuple
    inference: tuple
    ttft: tuple
    tbt: tuple
    compacted: int
    aborted: int


@dataclass(frozen=True)
class SessionFacts:
    retained: RetainedSession
    usage: TokenFacts
    tools: ToolFacts
    timing: TimingFacts
    cache_policy: dict
