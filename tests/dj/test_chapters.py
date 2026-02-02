"""Tests for the chapters module."""

import pytest

from voice_mode.dj.chapters import (
    Chapter,
    convert_cue_to_ffmetadata,
    get_chapter_count,
    parse_cue_content,
    parse_cue_time,
)


class TestParseCueTime:
    """Tests for parse_cue_time function."""

    def test_basic_time(self):
        """Test basic time conversion."""
        assert parse_cue_time("01:00:00") == 60000  # 1 minute

    def test_with_frames(self):
        """Test time with frames."""
        # 75 frames per second, so 37 frames = ~493ms
        result = parse_cue_time("00:10:37")
        assert result == 10493  # 10 seconds + 493ms

    def test_zero_time(self):
        """Test zero time."""
        assert parse_cue_time("00:00:00") == 0

    def test_longer_time(self):
        """Test longer duration."""
        # 29 minutes, 4 seconds, 29 frames
        result = parse_cue_time("29:04:29")
        expected = (29 * 60 + 4) * 1000 + int(29 * 1000 / 75)
        assert result == expected

    def test_invalid_format(self):
        """Test invalid format returns 0."""
        assert parse_cue_time("invalid") == 0
        assert parse_cue_time("01:00") == 0


class TestParseCueContent:
    """Tests for parse_cue_content function."""

    def test_simple_cue(self):
        """Test parsing a simple CUE file."""
        cue_content = '''FILE "album.mp3" MP3
TRACK 01 AUDIO
    TITLE "First Track"
    PERFORMER "Artist One"
    INDEX 01 00:00:00
TRACK 02 AUDIO
    TITLE "Second Track"
    PERFORMER "Artist Two"
    INDEX 01 03:30:00
'''
        chapters = parse_cue_content(cue_content)

        assert len(chapters) == 2
        assert chapters[0].title == "First Track"
        assert chapters[0].performer == "Artist One"
        assert chapters[0].start_ms == 0
        assert chapters[1].title == "Second Track"
        assert chapters[1].performer == "Artist Two"
        assert chapters[1].start_ms == 210000  # 3:30

    def test_no_performer(self):
        """Test parsing CUE without performer info."""
        cue_content = '''TRACK 01 AUDIO
    TITLE "Track Name"
    INDEX 01 01:00:00
'''
        chapters = parse_cue_content(cue_content)

        assert len(chapters) == 1
        assert chapters[0].title == "Track Name"
        assert chapters[0].performer is None

    def test_ignores_file_level_metadata(self):
        """Test that file-level TITLE/PERFORMER are ignored."""
        cue_content = '''TITLE "Album Title"
PERFORMER "Album Artist"
FILE "album.mp3" MP3
TRACK 01 AUDIO
    TITLE "Track Title"
    INDEX 01 00:00:00
'''
        chapters = parse_cue_content(cue_content)

        assert len(chapters) == 1
        assert chapters[0].title == "Track Title"

    def test_sorts_by_start_time(self):
        """Test that chapters are sorted by start time."""
        cue_content = '''TRACK 02 AUDIO
    TITLE "Second"
    INDEX 01 05:00:00
TRACK 01 AUDIO
    TITLE "First"
    INDEX 01 00:00:00
'''
        chapters = parse_cue_content(cue_content)

        assert len(chapters) == 2
        assert chapters[0].title == "First"
        assert chapters[1].title == "Second"


class TestConvertCueToFfmetadata:
    """Tests for convert_cue_to_ffmetadata function."""

    def test_basic_conversion(self):
        """Test basic CUE to FFmetadata conversion."""
        cue_content = '''TRACK 01 AUDIO
    TITLE "First Track"
    INDEX 01 00:00:00
TRACK 02 AUDIO
    TITLE "Second Track"
    INDEX 01 03:00:00
'''
        result = convert_cue_to_ffmetadata(cue_content)

        assert ";FFMETADATA1" in result
        assert "[CHAPTER]" in result
        assert "TIMEBASE=1/1000" in result
        assert "START=0" in result
        assert "START=180000" in result
        assert "title=First Track" in result
        assert "title=Second Track" in result

    def test_with_performer(self):
        """Test that performer is appended to title."""
        cue_content = '''TRACK 01 AUDIO
    TITLE "Song"
    PERFORMER "Artist"
    INDEX 01 00:00:00
'''
        result = convert_cue_to_ffmetadata(cue_content)

        assert "title=Song - Artist" in result

    def test_end_times_calculated(self):
        """Test that END times are calculated correctly."""
        cue_content = '''TRACK 01 AUDIO
    TITLE "First"
    INDEX 01 00:00:00
TRACK 02 AUDIO
    TITLE "Second"
    INDEX 01 01:00:00
'''
        result = convert_cue_to_ffmetadata(cue_content)

        # First chapter should end at start of second
        assert "END=60000" in result

    def test_with_duration(self):
        """Test that duration affects last chapter's end time."""
        cue_content = '''TRACK 01 AUDIO
    TITLE "Only Track"
    INDEX 01 00:00:00
'''
        result = convert_cue_to_ffmetadata(cue_content, duration_ms=300000)

        assert "END=300000" in result

    def test_without_duration(self):
        """Test default end time for last chapter."""
        cue_content = '''TRACK 01 AUDIO
    TITLE "Only Track"
    INDEX 01 00:00:00
'''
        result = convert_cue_to_ffmetadata(cue_content)

        # Default is start + 1 hour
        assert "END=3600000" in result


class TestGetChapterCount:
    """Tests for get_chapter_count function."""

    def test_count(self):
        """Test counting chapters."""
        cue_content = '''TRACK 01 AUDIO
    INDEX 01 00:00:00
TRACK 02 AUDIO
    INDEX 01 01:00:00
TRACK 03 AUDIO
    INDEX 01 02:00:00
'''
        assert get_chapter_count(cue_content) == 3

    def test_empty(self):
        """Test empty CUE file."""
        assert get_chapter_count("") == 0


# Sample MFP-style CUE content for integration testing
MFP_SAMPLE_CUE = '''REM GENRE "Electronic"
REM DATE "2014"
PERFORMER "Julien Mier"
TITLE "Music For Programming - Episode 49"
FILE "music_for_programming_49-julien_mier.mp3" MP3
  TRACK 01 AUDIO
    TITLE "Intro"
    PERFORMER "Various"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "Deep Focus"
    PERFORMER "Ambient Artist"
    INDEX 01 05:23:45
  TRACK 03 AUDIO
    TITLE "Flow State"
    PERFORMER "Electronic Producer"
    INDEX 01 12:45:30
'''


class TestMfpCueConversion:
    """Integration tests with MFP-style CUE content."""

    def test_mfp_style_cue(self):
        """Test conversion of MFP-style CUE file."""
        result = convert_cue_to_ffmetadata(MFP_SAMPLE_CUE)

        assert ";FFMETADATA1" in result
        # Should have 3 tracks
        assert result.count("[CHAPTER]") == 3
        assert "title=Intro - Various" in result
        assert "title=Deep Focus - Ambient Artist" in result

    def test_mfp_chapter_count(self):
        """Test chapter count for MFP content."""
        assert get_chapter_count(MFP_SAMPLE_CUE) == 3
