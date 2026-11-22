"""`voicemode service health SERVICE` for every SERVICE it accepts (VM-2649).

`voicemode` and `mlx-audio` are valid choices that the command never handled;
PR #517 made that unhandled branch exit 1, so a monitor would have flipped to
red with no service change. Both are now handled.
"""

import socket
import subprocess
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from voice_mode.cli import service_health


def _curl(stdout='{"status": "ok"}', returncode=0):
    return subprocess.CompletedProcess(['curl'], returncode, stdout, '')


@pytest.mark.parametrize('name, port, path', [
    ('whisper', 2022, '/health'),
    ('kokoro', 8880, '/health'),
])
def test_http_services_use_their_health_route(name, port, path):
    with patch('subprocess.run', return_value=_curl()) as run:
        result = CliRunner().invoke(service_health, [name])
    assert result.exit_code == 0, result.output
    assert run.call_args.args[0][-1] == f'http://127.0.0.1:{port}{path}'
    assert 'is responding' in result.output


def test_mlx_audio_is_handled():
    body = '{"object": "list", "data": []}'
    with patch('voice_mode.config.MLX_AUDIO_PORT', 8890), \
         patch('subprocess.run', return_value=_curl(body)) as run:
        result = CliRunner().invoke(service_health, ['mlx-audio'])
    assert result.exit_code == 0, result.output
    assert run.call_args.args[0][-1] == 'http://127.0.0.1:8890/v1/models'
    assert 'mlx-audio is responding' in result.output


def test_mlx_audio_list_body_does_not_crash():
    with patch('subprocess.run', return_value=_curl('[]')):
        result = CliRunner().invoke(service_health, ['mlx-audio'])
    assert result.exit_code == 0
    assert 'is responding' in result.output


def test_voicemode_listening():
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        with patch('voice_mode.config.SERVE_PORT', port):
            result = CliRunner().invoke(service_health, ['voicemode'])
    finally:
        server.close()
    assert result.exit_code == 0, result.output
    assert f'listening on port {port}' in result.output


def test_voicemode_not_listening_is_reported_not_unknown():
    probe = socket.socket()
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
    probe.close()
    with patch('voice_mode.config.SERVE_PORT', port):
        result = CliRunner().invoke(service_health, ['voicemode'])
    assert result.exit_code == 0
    assert 'Unknown service' not in result.output
    assert f'not responding on port {port}' in result.output
