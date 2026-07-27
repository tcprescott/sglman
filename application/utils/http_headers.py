"""Header-value sanitisation for response headers built from arbitrary text.

HTTP header values are encoded latin-1 when the response is serialized, so a
single character outside that range — an emoji, a ``→``, a ``✓`` — raises
``UnicodeEncodeError`` *after* the handler has returned, taking the whole
response with it. A header set on every response (``X-Fun-Fact``) turns that
into a site-wide outage, so the text is reduced here rather than trusted.
"""

# Punctuation that appears in prose and has a clean latin-1 equivalent, mapped
# so the common cases stay readable instead of degrading to '?'.
_HEADER_TRANS = str.maketrans({
    '–': '-',   # en-dash
    '—': '-',   # em-dash
    '‘': "'",   # left single quote
    '’': "'",   # right single quote
    '“': '"',   # left double quote
    '”': '"',   # right double quote
    '·': '.',   # middle dot
})


def header_safe(text: str) -> str:
    """Reduce ``text`` to a value an HTTP header can carry.

    Substitutes the punctuation above, collapses all whitespace (which also
    strips CR/LF, so a stray newline can never split the header block), and
    replaces anything still outside latin-1 with ``?``.
    """
    collapsed = ' '.join(text.translate(_HEADER_TRANS).split())
    return collapsed.encode('latin-1', 'replace').decode('latin-1')
