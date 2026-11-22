"""whisper.cpp CUDA build helpers (VM-2649, from the VM-2621 review of PR #517).

- nvcc is looked for in /usr/local/cuda/bin as well as on PATH: NVIDIA's own
  installers put it there and leave PATH alone.
- A CUDA host compiler the user exported (CUDAHOSTCXX / NVCC_CCBIN) is kept.
"""

import os
from unittest.mock import patch

import voice_mode.tools.whisper.install as w


def _exe(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('#!/bin/sh\n')
    path.chmod(0o755)
    return str(path)


class TestFindNvcc:
    def test_on_path_wins(self):
        with patch.object(w.shutil, 'which', return_value='/opt/cuda/bin/nvcc'):
            assert w.find_nvcc() == '/opt/cuda/bin/nvcc'

    def test_falls_back_to_usr_local_cuda(self, tmp_path):
        nvcc = _exe(tmp_path / 'cuda' / 'bin' / 'nvcc')
        with patch.object(w.shutil, 'which', return_value=None), \
             patch.object(w, 'CUDA_DEFAULT_NVCC', nvcc):
            assert w.find_nvcc() == nvcc

    def test_none_when_absent(self, tmp_path):
        with patch.object(w.shutil, 'which', return_value=None), \
             patch.object(w, 'CUDA_DEFAULT_NVCC', str(tmp_path / 'missing' / 'nvcc')):
            assert w.find_nvcc() is None


class TestCudaBuildSettings:
    def test_picks_a_host_compiler_when_none_exported(self):
        env = {'PATH': '/usr/bin'}
        with patch.object(w, 'cuda_host_compiler_override', return_value=('/usr/bin/g++-14', None)), \
             patch.object(w.shutil, 'which', return_value='/usr/bin/nvcc'):
            flags = w.cuda_build_settings(env, '/usr/bin/nvcc')
        assert flags == ['-DGGML_CUDA=ON', '-DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-14']
        assert env['CUDAHOSTCXX'] == env['NVCC_CCBIN'] == '/usr/bin/g++-14'

    def test_exported_cudahostcxx_is_kept(self):
        env = {'PATH': '/usr/bin', 'CUDAHOSTCXX': '/opt/gcc-12/bin/g++'}
        with patch.object(w, 'cuda_host_compiler_override') as override, \
             patch.object(w.shutil, 'which', return_value='/usr/bin/nvcc'):
            flags = w.cuda_build_settings(env, '/usr/bin/nvcc')
        override.assert_not_called()
        assert flags == ['-DGGML_CUDA=ON']
        assert env['CUDAHOSTCXX'] == '/opt/gcc-12/bin/g++'
        assert 'NVCC_CCBIN' not in env

    def test_exported_nvcc_ccbin_is_kept(self):
        env = {'PATH': '/usr/bin', 'NVCC_CCBIN': '/opt/gcc-12/bin/g++'}
        with patch.object(w, 'cuda_host_compiler_override') as override, \
             patch.object(w.shutil, 'which', return_value='/usr/bin/nvcc'):
            w.cuda_build_settings(env, '/usr/bin/nvcc')
        override.assert_not_called()
        assert env['NVCC_CCBIN'] == '/opt/gcc-12/bin/g++'
        assert 'CUDAHOSTCXX' not in env

    def test_nvcc_off_path_goes_on_the_build_path(self):
        env = {'PATH': '/usr/bin'}
        with patch.object(w, 'cuda_host_compiler_override', return_value=(None, None)), \
             patch.object(w.shutil, 'which', return_value=None):
            w.cuda_build_settings(env, '/usr/local/cuda/bin/nvcc')
        assert env['PATH'].split(os.pathsep)[0] == '/usr/local/cuda/bin'

    def test_nvcc_on_path_leaves_path_alone(self):
        env = {'PATH': '/usr/bin'}
        with patch.object(w, 'cuda_host_compiler_override', return_value=(None, None)), \
             patch.object(w.shutil, 'which', return_value='/usr/bin/nvcc'):
            w.cuda_build_settings(env, '/usr/bin/nvcc')
        assert env['PATH'] == '/usr/bin'
