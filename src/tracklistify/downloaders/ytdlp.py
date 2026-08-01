"""
yt-dlp video downloader implementation.
"""

# Standard library imports
import asyncio
import os
import time
from pathlib import Path
from typing import Optional

# Third-party imports
import yt_dlp

# Local/package imports
from tracklistify.config import get_config
from tracklistify.downloaders.base import Downloader
from tracklistify.utils.logger import get_logger

logger = get_logger(__name__)


class YTDLPLogger:
    """Custom logger for yt-dlp that integrates with our logging system."""

    def __init__(self):
        self._last_progress = 0
        self._show_progress = True
        self.downloaded_title = None

    def debug(self, msg):
        """Handle debug messages."""
        # Skip all debug messages
        pass

    def info(self, msg):
        """Handle info messages with proper formatting."""
        # Extract and format important messages
        if msg.startswith("[youtube] Extracting URL:"):
            logger.info(f"Extracting URL: {msg.split('URL: ')[1]}")
        elif msg.startswith("[download] Destination:"):
            logger.info(f"Destination: {msg.split('Destination: ')[1]}")
        elif "[ExtractAudio] Destination:" in msg:
            logger.info(f"Destination: {msg.split('Destination: ')[1]}")
        elif msg.startswith("Downloaded:"):
            # Extract and store the title
            self.downloaded_title = msg.split("Downloaded: ")[1].split(" (")[0].strip()
            logger.info(msg)
        # Skip all other messages

    def warning(self, msg):
        """Handle warning messages."""
        logger.warning(msg)

    def error(self, msg):
        """Handle error messages."""
        logger.error(msg)


class DownloadProgress:
    """Handles download progress display."""

    def __init__(self):
        self.last_line_length = 0

    def update(self, d):
        """Update progress display."""
        if d["status"] == "downloading":
            # Only show progress for meaningful updates
            if "_percent_str" in d and d.get("_percent_str", "0%")[:-1] != "0":
                progress = (
                    f"{d['_percent_str']} of "
                    f"{d.get('_total_bytes_str', 'Unknown size')} "
                    f"at {d.get('_speed_str', 'Unknown speed')}"
                )
                # Clear previous line and show progress
                print("\r" + " " * self.last_line_length, end="")
                print(f"\rDownloading: {progress}", end="")
                self.last_line_length = (
                    len(progress) + 12
                )  # account for "Downloading: "
        elif d["status"] == "finished":
            # Clear progress line and log completion
            print("\r" + " " * self.last_line_length + "\r", end="")
            if "_total_bytes_str" in d and "_elapsed_str" in d and "_speed_str" in d:
                logger.info(
                    f"Downloaded {d['_total_bytes_str']} in {d['_elapsed_str']} "
                    f"at {d['_speed_str']}"
                )


_progress_handler = DownloadProgress()


def progress_hook(d):
    """Handle download progress updates."""
    _progress_handler.update(d)


class YtDlpDownloader(Downloader):
    """yt-dlp video downloader."""

    def __init__(
        self,
        verbose: bool = False,
        quality: str = "192",
        format: str = "mp3",
        stream_copy: bool = False,
        temp_dir: Optional[str] = None,
    ):
        """Initialize yt-dlp downloader.

        Args:
            verbose: Enable verbose logging
            quality: Audio quality (bitrate)
            format: Output audio format (ignored when ``stream_copy=True``)
            stream_copy: If True, skip the FFmpegExtractAudio postprocessor
                and keep whatever audio codec YouTube serves (typically
                opus/webm or m4a). Faster for long mixes; downstream
                segmenting must also stream-copy.
            temp_dir: Per-invocation temp directory. When not provided,
                falls back to ``config.temp_dir``. Caller (AsyncApp)
                passes its own ``self.temp_dir`` so concurrent runs are
                isolated.
        """
        self.ffmpeg_path = self.get_ffmpeg_path()
        self.verbose = verbose
        self.quality = quality
        self.format = format
        self.stream_copy = stream_copy
        self.title = None
        self._logger = YTDLPLogger()
        self.config = get_config()
        self.temp_dir = temp_dir
        # Store the last extracted metadata from yt-dlp
        self.last_metadata = None
        # Track yt-dlp postprocessor timing so the user sees progress
        # during the otherwise-silent MP3 transcode phase.
        self._pp_started_at: Optional[float] = None
        logger.debug(
            f"Initialized yt-dlp downloader with ffmpeg at: {self.ffmpeg_path}"
        )
        logger.debug(
            f"Settings - Quality: {quality}kbps, Format: {format}, "
            f"stream_copy: {stream_copy}, temp_dir: {temp_dir}"
        )

    def _postprocessor_hook(self, d: dict) -> None:
        """Log yt-dlp postprocessor lifecycle so long transcodes aren't silent.

        yt-dlp can fire ``started`` more than once per postprocessor (outer
        lifecycle + inner ffmpeg). De-dup by only logging on the first
        ``started`` of a given pass — the matching ``finished`` resets the
        guard so the next pass logs again.
        """
        status = d.get("status")
        pp_name = d.get("postprocessor", "")
        if status == "started" and self._pp_started_at is None:
            self._pp_started_at = time.monotonic()
            logger.info(f"Post-processing audio (yt-dlp {pp_name})...")
        elif status == "finished" and self._pp_started_at is not None:
            elapsed = time.monotonic() - self._pp_started_at
            logger.info(f"Post-processing done in {elapsed:.1f}s")
            self._pp_started_at = None

    async def download(self, url: str) -> Optional[str]:
        """Download video from URL.

        Args:
            url: yt-dlp video URL

        Returns:
            Path to downloaded file
        """
        temp_dir = Path(self.temp_dir or self.config.temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Starting yt-dlp download: {url}")

        ydl_opts = {
            "format": "bestaudio/best",
            "ffmpeg_location": self.ffmpeg_path,
            "outtmpl": os.path.join(temp_dir, "%(id)s.%(ext)s"),
            "verbose": True,  # Always set to False to control output
            "quiet": True,
            "logger": self._logger,
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [self._postprocessor_hook],
            "no_warnings": True,  # Suppress unnecessary warnings
            # Bound the fetch to the first entry. A SoundCloud ``/sets/``
            # URL is a playlist, and ``extract_info(download=True)`` would
            # otherwise download EVERY track in it before returning —
            # unwrapping the returned metadata afterwards is far too late.
            # Observed against a real 15-track set: 606MB pulled across 6
            # tracks before the run was killed. We only ever process one
            # track, so fetch exactly one.
            "playlist_items": "1",
        }

        # Only attach the MP3 transcode postprocessor when stream-copy is
        # off. When on, we keep the source format (opus/webm/m4a) and let
        # the segmenter stream-copy it.
        if not self.stream_copy:
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": self.format,
                    "preferredquality": self.quality,
                }
            ]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # First get video info without downloading
                logger.debug("Extracting video information...")
                info = await asyncio.to_thread(ydl.extract_info, url, download=True)

                if info is None:
                    logger.error("Failed to extract video information")
                    raise ValueError("Failed to extract video information")

                # Unwrap single-entry playlist containers (notably
                # SoundCloud ``/sets/`` URLs). yt-dlp returns a playlist
                # dict whose id/ext/duration describe the *set*, not the
                # track; without unwrapping to ``entries[0]`` the wrong
                # metadata propagates into last_metadata (→ cache sidecar +
                # mix_info) and ``prepare_filename`` builds a path from the
                # set id. ``outtmpl`` is ``%(id)s.%(ext)s``, so the
                # container's id yields the wrong filename too. Unwrap
                # before anything reads ``info`` downstream.
                if info.get("_type") == "playlist":
                    entries = info.get("entries") or []
                    if entries:
                        if len(entries) > 1:
                            # Only the first entry is processed. Warn at
                            # default verbosity — a silently truncated set
                            # produces a tracklist for one track and caches
                            # it under the set's URL with no TTL, which
                            # looks like a correct result.
                            logger.warning(
                                f"URL resolved to a {len(entries)}-track set; "
                                f"processing only the first "
                                f"({entries[0].get('title', 'unknown')!r}). "
                                f"Pass a direct track URL to select another."
                            )
                        else:
                            logger.debug(
                                "Unwrapping single-entry playlist container "
                                "-> entries[0]"
                            )
                        info = entries[0]
                    else:
                        # Zero entries with the container still in hand.
                        # Falling through would leave ``info`` as the *set*
                        # — silently reinstating the exact wrong-metadata
                        # bug the unwrap above exists to fix, and then
                        # building an output path from the set id that no
                        # file was ever written to. Reachable for a
                        # private, deleted, or geo-blocked set, where
                        # yt-dlp returns the container with an empty
                        # ``tracks`` list. Fail loudly instead.
                        logger.error(
                            f"URL resolved to a playlist container with no "
                            f"downloadable entries (id="
                            f"{info.get('id', 'unknown')!r}); it may be "
                            f"private, deleted, or region-locked."
                        )
                        raise ValueError(f"No downloadable entries found for {url}")

                # Persist full metadata for later access
                self.last_metadata = info

                # Resolve the output path. Prefer the path yt-dlp actually
                # wrote (``requested_downloads[0]["filepath"]``) — strictly
                # more robust than reconstructing via ``prepare_filename``,
                # which misses extension changes the muxing postprocessor
                # makes (notably the MP3 transcode). Fall back to the
                # reconstruct+glob path when ``requested_downloads`` is
                # absent (older yt-dlp / stream-copy cases).
                output_path: Optional[str] = None
                requested = info.get("requested_downloads") or []
                if requested and requested[0].get("filepath"):
                    output_path = requested[0]["filepath"]
                elif requested:
                    # yt-dlp reported a download but gave no path. Distinct
                    # from "no requested_downloads at all" (the documented
                    # older-yt-dlp fallback), and worth saying so — this is
                    # the branch that silently degrades to the weaker
                    # reconstruct path in exactly the muxing cases the
                    # filepath preference was added to handle.
                    logger.debug(
                        f"requested_downloads present but carries no "
                        f"filepath ({requested[0]!r}); falling back to "
                        f"prepare_filename reconstruction."
                    )

                if output_path is None:
                    filename = ydl.prepare_filename(info)
                    if self.stream_copy:
                        candidate = Path(filename)
                        if not candidate.exists():
                            # Fall back to globbing — yt-dlp may have
                            # renamed the extension during muxing.
                            matches = list(candidate.parent.glob(candidate.stem + ".*"))
                            if matches:
                                candidate = matches[0]
                            else:
                                # Reconstruct missed and the glob found
                                # nothing: returning this path would report
                                # success for a file that does not exist,
                                # and the failure would first surface in
                                # split_audio as "Could not read audio
                                # file" — several frames from the cause.
                                logger.error(
                                    f"Download reported success but no file "
                                    f"was found at {candidate} or matching "
                                    f"{candidate.stem}.* in "
                                    f"{candidate.parent}"
                                )
                                raise ValueError(f"Downloaded file not found for {url}")
                        output_path = str(candidate)
                    else:
                        output_path = str(Path(filename).with_suffix(f".{self.format}"))

                # Set instance variables for external use
                self.title = info.get("title", "Unknown title")
                self.uploader = info.get("uploader", "Unknown artist")
                self.duration = info.get("duration", 0)
                logger.info(
                    f"Downloaded: {self.title} by {self.uploader} ({self.duration}s)"
                )
                logger.debug(f"Output file: {output_path}")
                return output_path

        except Exception as e:
            if "Private video" in str(e):
                logger.error(f"Cannot download private video: {url}")
            else:
                logger.error(f"Download failed: {e}")
            raise

    def get_last_metadata(self) -> Optional[dict]:
        """Expose the full yt-dlp info dict from the most recent download."""
        return self.last_metadata
