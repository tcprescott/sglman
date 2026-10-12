"""The Tiptap bundle MarkdownEditor imports must ship with the repo, or the editor and the dialog around it render empty."""

from pathlib import Path

from theme.markdown_editor import MarkdownEditor

DIST = Path(MarkdownEditor.__module__.replace('.', '/')) / 'dist'


def test_the_vendored_bundle_is_in_the_checkout():
    assert (DIST / 'index.js').is_file()
    assert (DIST / 'THIRD_PARTY_LICENSES.txt').is_file()
