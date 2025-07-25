#!/usr/bin/env python
"""
Test concurrent operations and stdio protection.

These tests verify that:
- Concurrent audio operations don't break stdio
- Sounddevice stderr redirection is properly handled
- Lock mechanism prevents race conditions
"""

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, Mock
import pytest
import numpy as np

# Set required environment variables before imports
os.environ['OPENAI_API_KEY'] = os.environ.get('OPENAI_API_KEY', 'test-key')

# Import from the appropriate modules
from voice_mode.config import audio_operation_lock
from voice_mode.tools.converse import record_audio, speech_to_text
from voice_mode.shared import (
    disable_sounddevice_stderr_redirect,
)


class TestStdioProtection:
    """Test stdio protection mechanisms"""
    
    def test_sounddevice_stderr_redirect_disabled(self):
        """Test that sounddevice stderr redirection is disabled"""
        import sounddevice as sd
        
        # Check if our workaround has been applied
        if hasattr(sd, '_sounddevice'):
            if hasattr(sd._sounddevice, '_ignore_stderr'):
                # The function should be replaced with a no-op
                assert sd._sounddevice._ignore_stderr() is None
        
        if hasattr(sd, '_ignore_stderr'):
            # The function should be replaced with a no-op
            assert sd._ignore_stderr() is None
    
    @pytest.mark.asyncio
    async def test_concurrent_operations_protected(self):
        """Test that concurrent operations are serialized by lock"""
        # Track operation order
        operation_order = []
        
        async def mock_operation(name: str):
            operation_order.append(f"{name}_start")
            await asyncio.sleep(0.1)  # Simulate work
            operation_order.append(f"{name}_end")
            return name
        
        # Test direct lock usage
        async def task1():
            async with audio_operation_lock:
                await mock_operation("task1")
        
        async def task2():
            async with audio_operation_lock:
                await mock_operation("task2")
        
        # Start two operations concurrently
        await asyncio.gather(task1(), task2())
        
        # Verify operations were serialized (not interleaved)
        assert operation_order == [
            "task1_start", "task1_end",
            "task2_start", "task2_end"
        ] or operation_order == [
            "task2_start", "task2_end",
            "task1_start", "task1_end"
        ]
    
    def test_stdio_restored_after_record(self):
        """Test that stdio is restored after recording"""
        original_stdin = sys.stdin
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        with patch('sounddevice.rec') as mock_rec, \
             patch('sounddevice.wait') as mock_wait:
            
            # Mock recording
            mock_rec.return_value = np.array([[100], [200]], dtype=np.int16)
            
            # Record audio
            result = record_audio(1.0)
            
            # Verify stdio is unchanged
            assert sys.stdin is original_stdin
            assert sys.stdout is original_stdout
            assert sys.stderr is original_stderr
    
    def test_stdio_restored_on_error(self):
        """Test that stdio is restored even when recording fails"""
        original_stdin = sys.stdin
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        with patch('voice_mode.tools.converse.sd.rec') as mock_rec, \
             patch('voice_mode.tools.converse.sd.wait') as mock_wait:
            # Make recording fail
            mock_rec.side_effect = Exception("Recording failed")
            
            # Try to record (should fail)
            result = record_audio(1.0)
            
            # Should return empty array on error
            assert len(result) == 0
            
            # Verify stdio is still unchanged
            assert sys.stdin is original_stdin
            assert sys.stdout is original_stdout
            assert sys.stderr is original_stderr


class TestConcurrentVoiceOperations:
    """Test concurrent voice operations"""
    
    @pytest.mark.asyncio
    async def test_lock_prevents_concurrent_audio(self):
        """Test that the lock prevents concurrent audio operations"""
        # Create a lock in the current event loop
        test_lock = asyncio.Lock()
        
        # This test verifies the lock is working by timing operations
        start_times = []
        end_times = []
        
        async def timed_operation(name: str):
            async with test_lock:
                start_times.append((name, asyncio.get_event_loop().time()))
                await asyncio.sleep(0.1)  # Simulate audio operation
                end_times.append((name, asyncio.get_event_loop().time()))
        
        # Run operations concurrently
        await asyncio.gather(
            timed_operation("op1"),
            timed_operation("op2"),
            timed_operation("op3")
        )
        
        # Sort by time
        start_times.sort(key=lambda x: x[1])
        end_times.sort(key=lambda x: x[1])
        
        # Verify no overlap - each operation should end before the next starts
        for i in range(len(end_times) - 1):
            assert end_times[i][1] <= start_times[i + 1][1], \
                f"Operation {end_times[i][0]} overlapped with {start_times[i + 1][0]}"


class TestErrorRecovery:
    """Test error recovery mechanisms"""
    
    @pytest.mark.asyncio
    async def test_broken_pipe_handling(self):
        """Test handling of broken pipe errors"""
        # This would test the main() function's error handling
        # but it's complex to test without actually running the server
        pass
    
    @pytest.mark.asyncio
    async def test_lock_release_on_error(self):
        """Test that lock is released even when operations fail"""
        operation_count = 0
        
        async def failing_operation():
            nonlocal operation_count
            async with audio_operation_lock:
                operation_count += 1
                if operation_count == 1:
                    raise Exception("First operation fails")
                return "success"
        
        # First operation should fail
        with pytest.raises(Exception):
            await failing_operation()
        
        # Second operation should succeed (lock was released)
        result = await failing_operation()
        assert result == "success"
        assert operation_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])