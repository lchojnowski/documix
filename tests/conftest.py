import json
import os

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
