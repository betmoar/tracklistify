"""The package's public metadata attributes resolve (#89).

`__all__` is a contract: `from tracklistify import *` binds exactly the
names it lists, and Python raises AttributeError if one is missing. Before
the fix `__all__` named four attributes that were never defined — the list
was assigned inside a function body, where it was a local — so a star
import raised on the first name.
"""

import pytest

import tracklistify


def test_all_names_resolve():
    """Every name in __all__ is actually an attribute of the module."""
    missing = [n for n in tracklistify.__all__ if not hasattr(tracklistify, n)]
    assert not missing, f"__all__ promises names the module lacks: {missing}"


def test_star_import_succeeds():
    """`from tracklistify import *` must not raise.

    This is the assertion that would have caught the original bug: it fails
    on the first unbound name in __all__.
    """
    ns: dict = {}
    exec("from tracklistify import *", ns)  # noqa: S102

    for name in tracklistify.__all__:
        assert name in ns, f"{name} in __all__ but not bound by star import"


def test_version_matches_distribution():
    """__version__ reports the installed distribution's version."""
    from importlib.metadata import version

    assert tracklistify.__version__ == version("tracklistify")


@pytest.mark.parametrize(
    "name, expected",
    [("__title__", "tracklistify"), ("__license__", "MIT")],
)
def test_metadata_values(name, expected):
    """Title and license come through with real values, not placeholders."""
    assert getattr(tracklistify, name) == expected


def test_author_is_populated():
    """__author__ resolves to something, via Author or Author-email.

    Which field carries it depends on how the backend rendered the
    pyproject `authors` table, so the test asserts non-emptiness rather
    than an exact string.
    """
    assert tracklistify.__author__
    assert tracklistify.__author__ != "unknown"


def test_unknown_attribute_still_raises():
    """__getattr__ must not turn every typo into a value."""
    with pytest.raises(AttributeError, match="no attribute 'does_not_exist'"):
        _ = tracklistify.does_not_exist


def test_lazy_names_appear_in_dir():
    """dir() includes the lazily-resolved attributes.

    A module __getattr__ is invisible to dir() unless __dir__ says
    otherwise, which breaks tab-completion and introspection.
    """
    listed = dir(tracklistify)
    for name in tracklistify.__all__:
        assert name in listed, f"{name} missing from dir()"


def test_metadata_is_not_read_at_import_time():
    """Importing the package must not touch importlib.metadata.

    The lookup walks the filesystem to locate the distribution. Paying for
    it on every `import tracklistify` would tax CLI startup, which reads
    none of these attributes.
    """
    import importlib.metadata

    calls = []
    original = importlib.metadata.metadata

    def _spy(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    importlib.metadata.metadata = _spy
    try:
        importlib.reload(tracklistify)
        assert not calls, f"metadata() called during import: {calls}"

        # ...but it IS called on first attribute access.
        _ = tracklistify.__version__
        assert calls, "metadata() was never called, even on access"
    finally:
        importlib.metadata.metadata = original
        importlib.reload(tracklistify)
