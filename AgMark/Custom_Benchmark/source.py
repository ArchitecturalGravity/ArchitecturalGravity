"""Read complete user prompt files without interpreting their contents."""
from pathlib import Path
from AgMark.shared.runtime.orchestration import TreatmentPrompt


def load_prompts(folder):
    if not isinstance(folder, str) or not folder.strip():
        raise ValueError("Choose a prompt folder containing files.")
    directory = Path(folder).expanduser()
    if not directory.is_dir():
        raise ValueError(f"Prompt folder is not a directory: {directory}")
    try:
        files = sorted(
            (path for path in directory.iterdir() if path.is_file()),
            key=lambda path: path.name,
        )
    except OSError as exc:
        raise ValueError(f"Cannot read prompt folder {directory}: {exc}") from exc
    if not files:
        raise ValueError("Prompt folder contains no top-level files.")
    prompts, errors = [], []
    for path in files:
        try:
            data = path.read_bytes()
            if not data.strip():
                raise ValueError("prompt is empty")
            prompts.append(TreatmentPrompt(path.name, data))
        except (OSError, ValueError) as exc:
            errors.append(f"{path.name}: {exc}")
    if errors:
        raise ValueError("Cannot prepare prompts:\n" + "\n".join(errors))
    return tuple(prompts)
