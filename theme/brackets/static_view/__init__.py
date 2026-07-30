"""Server-rendered, cacheable bracket HTML — the public "follow along" view.

The interactive bracket pages in ``pages/brackets.py`` are NiceGUI: every reader
holds an open websocket for as long as the tab is open, so a tournament with a
few hundred spectators costs a few hundred sockets on a single-worker app. This
package renders the *same* bracket as a plain HTML document that can be cached
and handed out by the thousand — no socket, no client framework, nothing to keep
alive. Consumed by ``pages/static_brackets.py``, which owns the routes and the
cache; everything here is pure and I/O-free.

* :mod:`.markup` — escaping plus the match-card / elimination-section DOM,
  mirroring :mod:`theme.brackets.cards`.
* :mod:`.data_tables` — standings, pairings and crosstables, mirroring
  :mod:`theme.brackets.tables`.
* :mod:`.document` — the page shell and the two whole-page renderers.
"""

from .document import (
    StaticBracketView,
    StaticIndexView,
    render_bracket_document,
    render_index_document,
)

__all__ = [
    'StaticBracketView',
    'StaticIndexView',
    'render_bracket_document',
    'render_index_document',
]
