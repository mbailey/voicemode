"""Hardware detection for service recommendations."""

import psutil

from .system import PlatformInfo


class HardwareInfo:
    """Detect and provide hardware recommendations."""

    def __init__(self, platform_info: PlatformInfo):
        self.platform = platform_info
        self.cpu_count = psutil.cpu_count(logical=False) or 1
        self.total_ram_gb = psutil.virtual_memory().total / (1024 ** 3)

    def is_apple_silicon(self) -> bool:
        """Check if running on Apple Silicon."""
        return self.platform.os_type == 'darwin' and self.platform.architecture == 'arm64'

    def is_arm64(self) -> bool:
        """Check if running on ARM64 architecture."""
        return self.platform.architecture == 'arm64'

    def get_ram_category(self) -> str:
        """Categorize RAM amount."""
        if self.total_ram_gb < 4:
            return 'low'
        elif self.total_ram_gb < 8:
            return 'medium'
        elif self.total_ram_gb < 16:
            return 'good'
        else:
            return 'excellent'

    def should_recommend_local_services(self) -> bool:
        """Determine if local services should be recommended."""
        # Apple Silicon is great for local services
        if self.is_apple_silicon():
            return True

        # Other ARM64 with good RAM
        if self.is_arm64() and self.total_ram_gb >= 8:
            return True

        # x86_64 with good specs
        if self.total_ram_gb >= 8 and self.cpu_count >= 4:
            return True

        return False

    def get_recommendation_message(self) -> str:
        """Get a recommendation message for local services."""
        if self.is_apple_silicon():
            return (
                f"Your Apple Silicon Mac with {self.total_ram_gb:.1f}GB RAM is great for local services.\n"
                f"Whisper and Kokoro will run fast and privately on your hardware."
            )
        elif self.is_arm64():
            if self.total_ram_gb >= 8:
                return (
                    f"Your ARM64 system with {self.total_ram_gb:.1f}GB RAM can run local services well.\n"
                    f"Recommended for privacy and offline use."
                )
            else:
                return (
                    f"Your ARM64 system has {self.total_ram_gb:.1f}GB RAM.\n"
                    f"Local services may work but cloud services might be more responsive."
                )
        else:  # x86_64
            if self.total_ram_gb >= 8 and self.cpu_count >= 4:
                return (
                    f"Your system ({self.cpu_count} cores, {self.total_ram_gb:.1f}GB RAM) can run local services.\n"
                    f"Recommended for privacy and offline use."
                )
            elif self.total_ram_gb >= 4:
                return (
                    f"Your system has {self.total_ram_gb:.1f}GB RAM.\n"
                    f"Local services will work but may be slower. Cloud services recommended for best performance."
                )
            else:
                return (
                    f"Your system has {self.total_ram_gb:.1f}GB RAM.\n"
                    f"Cloud services strongly recommended - local services may struggle."
                )

    def get_download_estimate(self) -> str:
        """Estimate download size for local services."""
        # Rough estimates:
        # Whisper: ~150MB (base model) to ~3GB (large model)
        # Kokoro: ~500MB
        # Total: ~2-4GB for full setup
        return "~2-4GB total (Whisper models + Kokoro)"
