import json
import os

from documix import config as _config

# The pre-anydoc default chains, for tests that exercise the legacy
# converters explicitly (they are opt-in now).
LEGACY_CONVERTER_CONFIG = {
    fmt: [name for name in names if name != 'tesseract']
    for fmt, names in _config.LEGACY_CONVERTERS.items()
}

RANKING_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'benchmark', 'converter_ranking.json'
)


def get_fastest_converter_config():
    """Return converter_config using fastest converters from benchmark results.

    Returns an empty dict if no benchmark results exist, which causes
    DocumentCompiler to use default converter ordering.
    """
    if not os.path.exists(RANKING_PATH):
        return {}
    with open(RANKING_PATH) as f:
        rankings = json.load(f)
    return {fmt: [convs[0]] for fmt, convs in rankings.items() if convs}


try:
    import pytest
except ImportError:  # pragma: no cover - conftest is also imported as a module
    pytest = None

if pytest is not None:
    from documix import tools as _tools

    @pytest.fixture(autouse=True)
    def _clear_tool_probe_cache():
        """Tool availability is cached per process; tests mock the probes
        differently from case to case, so start each one from a clean slate."""
        _tools.clear_cache()
        yield
        _tools.clear_cache()
