"""Presentation names for registrations; canonical selections remain untouched."""

from collections import Counter
import re
from typing import Literal

_NAMES = {
    "arcgrav.custom.benchmark.core": "Custom Benchmark",
    "openai.codex-cli": "OpenAI Codex CLI",
    "arcgrav.mock-model.runner": "Mock Model (Local Test)",
}


def registration_choices(
    options: tuple[str, ...], kind: Literal["benchmark", "runner"]
) -> dict[str, tuple[str, ...]]:
    """Return ordered labels without changing registration values.

    Unversioned demo choices keep their supplied text. Unknown registrations
    use a readable spelling of their ID; collisions retain explicit identity.
    """
    parsed = [option.rpartition("@") for option in options]
    counts = Counter(registration_id for registration_id, separator, _ in parsed if separator)
    labels = []
    for option, (registration_id, separator, version) in zip(options, parsed):
        if not separator or not registration_id or not version:
            labels.append(option)
            continue
        # Registration structure, not a concrete benchmark family, supplies a
        # concise display stem. Canonical values remain unchanged below.
        benchmark_stem = re.fullmatch(r"[^.]+\.(.+)\.benchmark\.core", registration_id)
        display_id = benchmark_stem.group(1) if kind == "benchmark" and benchmark_stem else registration_id
        name = _NAMES.get(registration_id) or " ".join(
            word.capitalize() for word in re.split(r"[._-]+", display_id) if word
        ) or registration_id
        if kind == "benchmark" and registration_id != "arcgrav.custom.benchmark.core":
            name += f" (v{version})"
        elif counts[registration_id] > 1:
            name += f" (Adapter v{version})"
        labels.append(name)
    duplicates = Counter(labels)
    # Include canonical identity only when friendly names cannot distinguish choices.
    labels = [f"{label} [{option}]" if duplicates[label] > 1 else label
              for option, label in zip(options, labels)]
    # Even an arbitrary supplied label may equal a disambiguated label.
    if len(set(labels)) != len(labels):
        labels = list(options)
    return {"option_labels": tuple(labels)}
