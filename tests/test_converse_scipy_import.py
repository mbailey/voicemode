"""
Regression tests for the scipy import in the converse tool (mbailey/voicemode#545).

record_audio_with_silence_detection used to run `from scipy import signal` inside its
per-chunk recording loop, so the first import happened after the sounddevice
InputStream had already opened, blocking the voice-activity-detection loop for
about 24 seconds on Windows. The fix moved the scipy.signal import to module load
time, before any stream can open.
"""

import dis
import sys
import types


class TestConverseScipyImport:
    """Tests ensuring scipy.signal is imported eagerly, not inside the recording loop."""

    def test_importing_converse_leaves_scipy_signal_in_sys_modules(self):
        """Importing voice_mode.tools.converse must populate sys.modules with scipy.signal."""
        import voice_mode.tools.converse  # noqa: F401

        assert "scipy.signal" in sys.modules

    def test_record_audio_with_silence_detection_has_no_scipy_import(self):
        """record_audio_with_silence_detection's bytecode must contain no scipy import."""
        from voice_mode.tools.converse import record_audio_with_silence_detection

        def walk_instructions(code):
            for instruction in dis.get_instructions(code):
                yield instruction
            for const in code.co_consts:
                if isinstance(const, types.CodeType):
                    yield from walk_instructions(const)

        scipy_imports = [
            instruction
            for instruction in walk_instructions(record_audio_with_silence_detection.__code__)
            if instruction.opname == "IMPORT_NAME"
            and (
                instruction.argval == "scipy"
                or instruction.argval.startswith("scipy.")
            )
        ]

        assert not scipy_imports, (
            "found scipy import(s) inside record_audio_with_silence_detection: "
            f"{scipy_imports}"
        )
