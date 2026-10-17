"""Converter chains.

Every converter is a function ``convert(path, ...) -> (text, method)`` that
returns ``(None, None)`` when it cannot produce output, so the chain moves on
to the next one. ``run_chain`` implements the first-success policy.
"""


def run_chain(order, dispatch, filepath, accept):
    """Try converters in ``order``; return the first result ``accept`` likes.

    ``dispatch`` maps converter names to callables taking the file path.
    Returns ``(None, None)`` when every converter declined.
    """
    for name in order:
        text, method = dispatch[name](filepath)
        if accept(text):
            return text, method
    return None, None
