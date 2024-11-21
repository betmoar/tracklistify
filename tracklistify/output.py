"""
Output formatting and file handling for Tracklistify.
"""

from datetime import datetime
from pathlib import Path
from typing import List, Optional
import json
import re
from .track import Track
from .logger import logger
from .config import get_config

class TracklistOutput:
    """Handles tracklist output in various formats."""
    
    def __init__(self, tracks: List[Track], mix_info: dict):
        """
        Initialize with tracks and mix information.
        
        Args:
            tracks: List of identified tracks
            mix_info: Dictionary containing mix metadata
        """
        self.tracks = tracks
        self.mix_info = mix_info
        self._config = get_config()
        self.output_dir = Path(self._config.output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    def _format_filename(self, extension: str) -> str:
        """
        Generate filename in format: [YYYYMMDD] Artist - Description.extension
        
        Args:
            extension: File extension without dot
            
        Returns:
            Formatted filename
        """
        # Get date in YYYYMMDD format
        mix_date = self.mix_info.get('date', datetime.now().strftime('%Y-%m-%d'))
        if isinstance(mix_date, str):
            try:
                mix_date = datetime.strptime(mix_date, '%Y-%m-%d').strftime('%Y%m%d')
            except ValueError:
                mix_date = datetime.now().strftime('%Y%m%d')
        
        # Get artist and description
        artist = self.mix_info.get('artist', 'Unknown Artist')
        description = self.mix_info.get('title', 'Unknown Mix')
        
        # Clean up special characters but preserve spaces and basic punctuation
        def clean_string(s: str) -> str:
            # Replace invalid filename characters with spaces
            s = re.sub(r'[<>:"/\\|?*]', ' ', s)
            # Replace multiple spaces with single space
            s = re.sub(r'\s+', ' ', s)
            # Strip leading/trailing spaces
            return s.strip()
        
        artist = clean_string(artist)
        description = clean_string(description)
        
        # Format filename
        return f"[{mix_date}] {artist} - {description}.{extension}"
    
    def save(self, format_type: str) -> Optional[Path]:
        """
        Save tracks in specified format.
        
        Args:
            format_type: Output format ('json', 'markdown', or 'm3u')
            
        Returns:
            Path to saved file, or None if format is invalid
        """
        if format_type == 'json':
            return self._save_json()
        elif format_type == 'markdown':
            return self._save_markdown()
        elif format_type == 'm3u':
            return self._save_m3u()
        else:
            logger.error(f"Invalid format type: {format_type}")
            return None
    
    def _save_json(self) -> Path:
        """Save tracks as JSON file."""
        output_file = self.output_dir / self._format_filename('json')
        
        data = {
            'mix_info': self.mix_info,
            'track_count': len(self.tracks),
            'analysis_info': {
                'timestamp': datetime.now().isoformat(),
                'track_count': len(self.tracks),
                'average_confidence': sum(t.confidence for t in self.tracks) / len(self.tracks) if self.tracks else 0,
                'min_confidence': min(t.confidence for t in self.tracks) if self.tracks else 0,
                'max_confidence': max(t.confidence for t in self.tracks) if self.tracks else 0,
            },
            'tracks': [
                {
                    'song_name': track.song_name,
                    'artist': track.artist,
                    'time_in_mix': track.time_in_mix,
                    'confidence': track.confidence,
                    'duration': track.duration if hasattr(track, 'duration') else None
                }
                for track in self.tracks
            ]
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
        logger.info(f"Saved JSON tracklist to: {output_file}")
        logger.info(f"Analysis Summary:")
        logger.info(f"- Total tracks: {data['analysis_info']['track_count']}")
        logger.info(f"- Average confidence: {data['analysis_info']['average_confidence']:.1f}%")
        logger.info(f"- Confidence range: {data['analysis_info']['min_confidence']:.1f}% - {data['analysis_info']['max_confidence']:.1f}%")
        return output_file
    
    def _save_markdown(self) -> Path:
        """Save tracks as Markdown file."""
        output_file = self.output_dir / self._format_filename('md')
        
        with open(output_file, 'w', encoding='utf-8') as f:
            # Write header
            f.write(f"# {self.mix_info.get('title', 'Unknown Mix')}\n\n")
            
            if self.mix_info.get('artist'):
                f.write(f"**Artist:** {self.mix_info['artist']}\n")
            if self.mix_info.get('date'):
                f.write(f"**Date:** {self.mix_info['date']}\n")
            f.write("\n## Tracklist\n\n")
            
            # Write tracks
            for i, track in enumerate(self.tracks, 1):
                f.write(f"{i}. **{track.time_in_mix}** - {track.artist} - {track.song_name}")
                if track.confidence < 80:
                    f.write(f" _(Confidence: {track.confidence:.0f}%)_")
                f.write("\n")
        
        logger.info(f"Saved Markdown tracklist to: {output_file}")
        return output_file
    
    def _save_m3u(self) -> Path:
        """Save tracks as M3U playlist."""
        output_file = self.output_dir / self._format_filename('m3u')
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            
            for track in self.tracks:
                duration = getattr(track, 'duration', -1)
                f.write(f"#EXTINF:{duration},{track.artist} - {track.song_name}\n")
                # Note: Since we don't have actual file paths, we add a comment with the time in mix
                f.write(f"# Time in mix: {track.time_in_mix}\n")
        
        logger.info(f"Saved M3U playlist to: {output_file}")
        return output_file
