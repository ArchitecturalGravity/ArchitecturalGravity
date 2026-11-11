"""Test-only Codex protocol simulator, never a production runner adapter."""
import json
from pathlib import Path

def load_registration():
    """Load isolated Codex transport-test metadata, not discoverable authority."""
    return json.loads(Path(__file__).with_name("fixture_registration.json").read_text())
