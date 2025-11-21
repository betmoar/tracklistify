"""
Tests for Issue #11: Spotify Encapsulation

Ensures SpotifyPlaylistExporter uses SpotifyProvider's public API
instead of accessing private attributes.
"""

# Standard library imports
import ast
from pathlib import Path

# Third-party imports
import pytest


class TestSpotifyEncapsulation:
    """Test that Spotify exporter uses proper encapsulation."""

    def test_exporter_does_not_access_session(self):
        """Ensure SpotifyPlaylistExporter doesn't access _session."""
        exporter_file = Path("src/tracklistify/exporters/spotify.py")

        with open(exporter_file) as f:
            content = f.read()

        # Check for direct _session access
        if "._session" in content or "self.spotify._session" in content:
            pytest.fail(
                "SpotifyPlaylistExporter accesses private _session attribute - "
                "should use public API methods instead"
            )

    def test_exporter_does_not_access_get_auth_headers(self):
        """Ensure SpotifyPlaylistExporter doesn't access _get_auth_headers."""
        exporter_file = Path("src/tracklistify/exporters/spotify.py")

        with open(exporter_file) as f:
            content = f.read()

        # Check for _get_auth_headers access
        if "_get_auth_headers" in content:
            pytest.fail(
                "SpotifyPlaylistExporter accesses private _get_auth_headers method - "
                "should use public API methods instead"
            )

    def test_exporter_does_not_access_api_request(self):
        """Ensure SpotifyPlaylistExporter doesn't access _api_request directly."""
        exporter_file = Path("src/tracklistify/exporters/spotify.py")

        with open(exporter_file) as f:
            content = f.read()

        # Check for _api_request access
        if "_api_request" in content:
            pytest.fail(
                "SpotifyPlaylistExporter accesses private _api_request method - "
                "should use public API methods instead"
            )

    def test_provider_has_create_playlist_method(self):
        """Ensure SpotifyProvider has public create_playlist method."""
        provider_file = Path("src/tracklistify/providers/spotify.py")

        with open(provider_file) as f:
            content = f.read()

        tree = ast.parse(content)

        # Find SpotifyProvider class
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "SpotifyProvider":
                method_names = [
                    item.name
                    for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                assert "create_playlist" in method_names, (
                    "SpotifyProvider should have a public create_playlist method"
                )
                return

        pytest.fail("SpotifyProvider class not found")

    def test_provider_has_add_tracks_to_playlist_method(self):
        """Ensure SpotifyProvider has public add_tracks_to_playlist method."""
        provider_file = Path("src/tracklistify/providers/spotify.py")

        with open(provider_file) as f:
            content = f.read()

        tree = ast.parse(content)

        # Find SpotifyProvider class
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "SpotifyProvider":
                method_names = [
                    item.name
                    for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                assert "add_tracks_to_playlist" in method_names, (
                    "SpotifyProvider should have a public add_tracks_to_playlist method"
                )
                return

        pytest.fail("SpotifyProvider class not found")

    def test_exporter_uses_create_playlist(self):
        """Ensure SpotifyPlaylistExporter calls create_playlist."""
        exporter_file = Path("src/tracklistify/exporters/spotify.py")

        with open(exporter_file) as f:
            content = f.read()

        # Should call the public method
        assert "self.spotify.create_playlist" in content, (
            "SpotifyPlaylistExporter should call spotify.create_playlist()"
        )

    def test_exporter_uses_add_tracks_to_playlist(self):
        """Ensure SpotifyPlaylistExporter calls add_tracks_to_playlist."""
        exporter_file = Path("src/tracklistify/exporters/spotify.py")

        with open(exporter_file) as f:
            content = f.read()

        # Should call the public method
        assert "self.spotify.add_tracks_to_playlist" in content, (
            "SpotifyPlaylistExporter should call spotify.add_tracks_to_playlist()"
        )


class TestSpotifyProviderPublicAPI:
    """Test SpotifyProvider public API methods exist with correct signatures."""

    def test_create_playlist_signature(self):
        """Test create_playlist has correct parameters."""
        provider_file = Path("src/tracklistify/providers/spotify.py")

        with open(provider_file) as f:
            content = f.read()

        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "SpotifyProvider":
                for item in node.body:
                    if (
                        isinstance(item, ast.AsyncFunctionDef)
                        and item.name == "create_playlist"
                    ):
                        # Get parameter names (excluding self)
                        param_names = [
                            arg.arg for arg in item.args.args if arg.arg != "self"
                        ]
                        assert "name" in param_names, (
                            "create_playlist should accept 'name' parameter"
                        )
                        return

        pytest.fail("create_playlist method not found")

    def test_add_tracks_to_playlist_signature(self):
        """Test add_tracks_to_playlist has correct parameters."""
        provider_file = Path("src/tracklistify/providers/spotify.py")

        with open(provider_file) as f:
            content = f.read()

        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "SpotifyProvider":
                for item in node.body:
                    if (
                        isinstance(item, ast.AsyncFunctionDef)
                        and item.name == "add_tracks_to_playlist"
                    ):
                        # Get parameter names (excluding self)
                        param_names = [
                            arg.arg for arg in item.args.args if arg.arg != "self"
                        ]
                        assert "playlist_id" in param_names, (
                            "add_tracks_to_playlist should accept 'playlist_id'"
                        )
                        assert "track_ids" in param_names, (
                            "add_tracks_to_playlist should accept 'track_ids'"
                        )
                        return

        pytest.fail("add_tracks_to_playlist method not found")

    def test_create_playlist_is_async(self):
        """Test create_playlist is an async method."""
        provider_file = Path("src/tracklistify/providers/spotify.py")

        with open(provider_file) as f:
            content = f.read()

        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "SpotifyProvider":
                for item in node.body:
                    if (
                        isinstance(item, ast.AsyncFunctionDef)
                        and item.name == "create_playlist"
                    ):
                        return  # Found async method

        pytest.fail("create_playlist should be an async method")

    def test_add_tracks_to_playlist_is_async(self):
        """Test add_tracks_to_playlist is an async method."""
        provider_file = Path("src/tracklistify/providers/spotify.py")

        with open(provider_file) as f:
            content = f.read()

        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "SpotifyProvider":
                for item in node.body:
                    if (
                        isinstance(item, ast.AsyncFunctionDef)
                        and item.name == "add_tracks_to_playlist"
                    ):
                        return  # Found async method

        pytest.fail("add_tracks_to_playlist should be an async method")
