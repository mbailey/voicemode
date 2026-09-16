"""Tests for dependency management system."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from voice_mode.utils.dependencies.cache import DependencyCache
from voice_mode.utils.dependencies.checker import detect_platform, check_dependency
from voice_mode.utils.dependencies.package_managers import (
    BrewManager,
    AptManager,
    DnfManager,
    OstreeBrewManager,
    RpmOstreeManager,
    get_package_manager,
    translate_to_brew,
)


class TestDependencyCache:
    """Test dependency caching behavior."""

    def test_cache_stores_present_packages(self):
        """Test that cache stores packages that are installed."""
        cache = DependencyCache()

        # Present package gets cached
        cache.set("ffmpeg", True)
        assert cache.get("ffmpeg") is True

    def test_cache_does_not_store_missing_packages(self):
        """Test that cache doesn't store missing packages."""
        cache = DependencyCache()

        # Missing package doesn't get cached
        cache.set("missing-pkg", False)
        assert cache.get("missing-pkg") is None

    def test_cache_clear(self):
        """Test cache clearing."""
        cache = DependencyCache()

        cache.set("ffmpeg", True)
        assert cache.get("ffmpeg") is True

        cache.clear()
        assert cache.get("ffmpeg") is None


class TestPlatformDetection:
    """Test platform detection logic."""

    @patch('platform.system')
    def test_detect_darwin(self, mock_system):
        """Test macOS detection."""
        mock_system.return_value = 'Darwin'
        assert detect_platform() == 'darwin'

    @patch('platform.system')
    @patch('os.path.exists')
    def test_detect_debian(self, mock_exists, mock_system):
        """Test Debian/Ubuntu detection."""
        mock_system.return_value = 'Linux'

        def exists_side_effect(path):
            if path == '/etc/debian_version':
                return True
            return False

        mock_exists.side_effect = exists_side_effect

        # Mock /proc/version to not contain WSL
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = 'Linux version 5.0'
            assert detect_platform() == 'debian'

    @patch('platform.system')
    @patch('os.path.exists')
    def test_detect_fedora(self, mock_exists, mock_system):
        """Test Fedora detection."""
        mock_system.return_value = 'Linux'

        def exists_side_effect(path):
            if path == '/etc/fedora-release':
                return True
            return False

        mock_exists.side_effect = exists_side_effect

        # Mock /proc/version to not contain WSL
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = 'Linux version 5.0'
            assert detect_platform() == 'fedora'


class TestPackageManagers:
    """Test package manager implementations."""

    @patch('shutil.which')
    def test_brew_manager_available(self, mock_which):
        """Test Brew manager detection."""
        mock_which.return_value = '/usr/local/bin/brew'
        manager = BrewManager()
        assert manager.check_available() is True

    @patch('shutil.which')
    def test_brew_manager_not_available(self, mock_which):
        """Test Brew manager when not installed."""
        mock_which.return_value = None
        manager = BrewManager()
        assert manager.check_available() is False

    @patch('subprocess.run')
    def test_brew_check_package_installed(self, mock_run):
        """Test checking if package is installed via Brew."""
        mock_run.return_value = Mock(returncode=0)
        manager = BrewManager()
        assert manager.check_package("ffmpeg") is True

    @patch('subprocess.run')
    def test_brew_check_package_not_installed(self, mock_run):
        """Test checking if package is not installed via Brew."""
        mock_run.return_value = Mock(returncode=1)
        manager = BrewManager()
        assert manager.check_package("ffmpeg") is False

    @patch('shutil.which')
    def test_apt_manager_available(self, mock_which):
        """Test APT manager detection."""
        mock_which.return_value = '/usr/bin/apt-get'
        manager = AptManager()
        assert manager.check_available() is True

    @patch('subprocess.run')
    def test_apt_check_package_installed(self, mock_run):
        """Test checking if package is installed via APT."""
        mock_run.return_value = Mock(returncode=0, stdout='ii  ffmpeg')
        manager = AptManager()
        assert manager.check_package("ffmpeg") is True

    @patch('shutil.which')
    def test_dnf_manager_available(self, mock_which):
        """Test DNF manager detection."""
        mock_which.return_value = '/usr/bin/dnf'
        manager = DnfManager()
        assert manager.check_available() is True

    @patch('subprocess.run')
    def test_dnf_check_package_installed(self, mock_run):
        """Test checking if package is installed via DNF."""
        mock_run.return_value = Mock(returncode=0)
        manager = DnfManager()
        assert manager.check_package("ffmpeg") is True


@patch('voice_mode.utils.dependencies.package_managers.platform.system', return_value='Linux')
@patch('voice_mode.utils.dependencies.package_managers.is_ostree_system', return_value=False)
class TestPackageManagerSelection:
    """Test automatic package manager selection on a traditional Linux distro.

    Both the OS and the ostree probe are pinned so these assert the intended
    branch on any host. Without that, they read the machine they run on: on a
    Fedora Atomic host the ostree branch returns before the dnf/apt/brew list is
    ever consulted, and on macOS the Darwin branch does.
    """

    @patch('voice_mode.utils.dependencies.package_managers.BrewManager.check_available')
    @patch('voice_mode.utils.dependencies.package_managers.DnfManager.check_available')
    @patch('voice_mode.utils.dependencies.package_managers.AptManager.check_available')
    def test_get_package_manager_brew(self, mock_apt, mock_dnf, mock_brew, _ostree, _sys):
        """Brew is the fallback when no native package manager is present."""
        mock_brew.return_value = True
        mock_dnf.return_value = False
        mock_apt.return_value = False
        manager = get_package_manager()
        assert isinstance(manager, BrewManager)

    @patch('voice_mode.utils.dependencies.package_managers.BrewManager.check_available')
    @patch('voice_mode.utils.dependencies.package_managers.DnfManager.check_available')
    def test_get_package_manager_dnf(self, mock_dnf, mock_brew, _ostree, _sys):
        """Test getting DNF manager when Brew not available."""
        mock_brew.return_value = False
        mock_dnf.return_value = True
        manager = get_package_manager()
        assert isinstance(manager, DnfManager)

    @patch('voice_mode.utils.dependencies.package_managers.BrewManager.check_available')
    @patch('voice_mode.utils.dependencies.package_managers.DnfManager.check_available')
    def test_dnf_preferred_over_brew(self, mock_dnf, mock_brew, _ostree, _sys):
        """The native manager wins when both are installed.

        dependencies.yaml supplies distro package names, so preferring Homebrew
        would hand it names it cannot resolve on a machine that has both.
        """
        mock_brew.return_value = True
        mock_dnf.return_value = True
        assert isinstance(get_package_manager(), DnfManager)

    @patch('voice_mode.utils.dependencies.package_managers.BrewManager.check_available')
    @patch('voice_mode.utils.dependencies.package_managers.DnfManager.check_available')
    @patch('voice_mode.utils.dependencies.package_managers.AptManager.check_available')
    def test_get_package_manager_apt(self, mock_apt, mock_dnf, mock_brew, _ostree, _sys):
        """Test getting APT manager when others not available."""
        mock_brew.return_value = False
        mock_dnf.return_value = False
        mock_apt.return_value = True
        manager = get_package_manager()
        assert isinstance(manager, AptManager)

    @patch('voice_mode.utils.dependencies.package_managers.BrewManager.check_available')
    @patch('voice_mode.utils.dependencies.package_managers.DnfManager.check_available')
    @patch('voice_mode.utils.dependencies.package_managers.AptManager.check_available')
    def test_get_package_manager_none_available(self, mock_apt, mock_dnf, mock_brew, _ostree, _sys):
        """Test error when no package manager is available."""
        mock_brew.return_value = False
        mock_dnf.return_value = False
        mock_apt.return_value = False

        with pytest.raises(RuntimeError, match="No supported package manager found"):
            get_package_manager()


@patch('voice_mode.utils.dependencies.package_managers.platform.system', return_value='Linux')
@patch('voice_mode.utils.dependencies.package_managers.is_ostree_system', return_value=True)
class TestPackageManagerSelectionOstree:
    """Selection on Fedora Atomic (Silverblue, Kinoite, Bazzite, Bluefin).

    `dnf install` can never succeed there -- /usr is read-only and Bazzite ships
    a dnf shim that refuses it -- so DnfManager must never be selected even
    though `dnf` is on PATH.
    """

    @patch('voice_mode.utils.dependencies.package_managers.get_homebrew_prefix')
    def test_ostree_with_homebrew(self, mock_prefix, _ostree, _sys):
        """Homebrew is the install path when present: no root, no reboot."""
        mock_prefix.return_value = '/home/linuxbrew/.linuxbrew'
        assert isinstance(get_package_manager(), OstreeBrewManager)

    @patch('voice_mode.utils.dependencies.package_managers.get_homebrew_prefix')
    def test_ostree_without_homebrew(self, mock_prefix, _ostree, _sys):
        """Without Homebrew, fall back to the manager that explains the options."""
        mock_prefix.return_value = None
        assert isinstance(get_package_manager(), RpmOstreeManager)

    @patch('voice_mode.utils.dependencies.package_managers.get_homebrew_prefix')
    @patch('voice_mode.utils.dependencies.package_managers.DnfManager.check_available',
           return_value=True)
    def test_ostree_never_selects_dnf(self, _dnf, mock_prefix, _ostree, _sys):
        """dnf on PATH must not win on Atomic -- installing with it cannot work."""
        mock_prefix.return_value = None
        assert not isinstance(get_package_manager(), DnfManager)


class TestBrewNameTranslation:
    """dependencies.yaml uses Fedora RPM names; Homebrew formulae differ."""

    def test_devel_suffix_is_stripped(self):
        """`brew install portaudio-devel` fails -- the formula is `portaudio`."""
        formulae, unmappable = translate_to_brew(['portaudio-devel', 'alsa-lib-devel'])
        assert formulae == ['portaudio', 'alsa-lib']
        assert unmappable == []

    def test_cargo_and_rust_collapse_to_one_formula(self):
        """cargo has no formula of its own; it ships inside rust."""
        formulae, unmappable = translate_to_brew(['cargo', 'rust'])
        assert formulae == ['rust']
        assert unmappable == []

    def test_unmappable_names_are_reported_not_guessed(self):
        formulae, unmappable = translate_to_brew(['portaudio', 'no-such-package'])
        assert formulae == ['portaudio']
        assert unmappable == ['no-such-package']
