"""Routing in the standalone installer's PackageInstaller (installer/).

The Fedora Atomic path is for ostree hosts in the Fedora family only. An ostree
host of another family (Endless OS is Debian) must take its own family's path,
and --dry-run must never run a real package manager there (VM-2621 review of
PR #517, findings G1 and N1; VM-2649).
"""

import pathlib
import sys
from unittest.mock import patch

import pytest

INSTALLER = pathlib.Path(__file__).resolve().parent.parent / 'installer'
if str(INSTALLER) not in sys.path:
    sys.path.insert(0, str(INSTALLER))

from voicemode_install.checker import PackageInfo  # noqa: E402
from voicemode_install.installer import PackageInstaller  # noqa: E402
from voicemode_install.system import PlatformInfo  # noqa: E402


def _platform(distribution, is_ostree):
    return PlatformInfo(
        os_type='linux',
        os_name=distribution,
        distribution=distribution,
        architecture='x86_64',
        is_ostree=is_ostree,
    )


def _packages(*names):
    return [PackageInfo(name=n, description=n, required=True, installed=False) for n in names]


def _installer(distribution, is_ostree, dry_run=False):
    with patch('voicemode_install.installer.get_homebrew_prefix', return_value=None), \
         patch('voicemode_install.system.get_homebrew_prefix', return_value=None):
        return PackageInstaller(_platform(distribution, is_ostree), dry_run=dry_run)


@pytest.mark.parametrize('distribution, is_ostree, expected', [
    ('fedora', True, True),
    ('fedora', False, False),
    ('debian', True, False),
    ('arch', True, False),
    ('suse', True, False),
    ('darwin', False, False),
])
def test_is_fedora_atomic(distribution, is_ostree, expected):
    assert _platform(distribution, is_ostree).is_fedora_atomic is expected


def test_dry_run_on_a_debian_ostree_host_runs_nothing():
    """G1: Endless OS --dry-run used to run real `sudo apt`."""
    installer = _installer('debian', True, dry_run=True)
    with patch('voicemode_install.installer.subprocess.run') as run, \
         patch.object(PackageInstaller, '_install_apt') as apt:
        assert installer.install_packages(_packages('ffmpeg')) is True
    run.assert_not_called()
    apt.assert_not_called()


@pytest.mark.parametrize('distribution', ['arch', 'suse', 'alpine'])
def test_non_fedora_ostree_never_takes_the_atomic_path(distribution, capsys):
    """N1: arch/suse ostree hosts were sent Fedora Atomic's brew/rpm-ostree advice."""
    installer = _installer(distribution, True)
    with patch.object(PackageInstaller, '_install_ostree') as ostree:
        assert installer.install_packages(_packages('ffmpeg')) is False
    ostree.assert_not_called()
    assert 'Unsupported distribution' in capsys.readouterr().out


def test_debian_ostree_takes_apt():
    installer = _installer('debian', True)
    with patch.object(PackageInstaller, '_install_apt', return_value=True) as apt, \
         patch.object(PackageInstaller, '_install_ostree') as ostree:
        assert installer.install_packages(_packages('ffmpeg')) is True
    apt.assert_called_once_with(['ffmpeg'])
    ostree.assert_not_called()


def test_fedora_atomic_still_takes_the_atomic_path():
    installer = _installer('fedora', True)
    with patch.object(PackageInstaller, '_install_ostree', return_value=True) as ostree, \
         patch.object(PackageInstaller, '_install_dnf') as dnf:
        assert installer.install_packages(_packages('ffmpeg')) is True
    ostree.assert_called_once_with(['ffmpeg'])
    dnf.assert_not_called()


def test_fedora_atomic_dry_run_reports_through_the_atomic_path():
    """On Atomic the dry run is reported by _install_ostree, which honours dry_run."""
    installer = _installer('fedora', True, dry_run=True)
    with patch.object(PackageInstaller, '_install_ostree', return_value=True) as ostree:
        assert installer.install_packages(_packages('ffmpeg')) is True
    ostree.assert_called_once_with(['ffmpeg'])
