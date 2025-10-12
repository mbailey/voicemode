"""Installation logging."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


class InstallLogger:
    """Log installation progress and results."""

    def __init__(self, log_path: Path = None):
        if log_path is None:
            voicemode_dir = Path.home() / '.voicemode'
            voicemode_dir.mkdir(exist_ok=True)
            log_path = voicemode_dir / 'install.log'

        self.log_path = log_path
        self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.events = []

    def log_event(self, event_type: str, message: str, details: Dict[str, Any] = None):
        """Log an installation event."""
        event = {
            'timestamp': datetime.now().isoformat(),
            'session_id': self.session_id,
            'type': event_type,
            'message': message,
        }

        if details:
            event['details'] = details

        self.events.append(event)

        # Append to log file
        with open(self.log_path, 'a') as f:
            f.write(json.dumps(event) + '\n')

    def log_start(self, system_info: Dict[str, Any]):
        """Log installation start."""
        self.log_event('start', 'Installation started', {'system': system_info})

    def log_check(self, component: str, packages_found: int, packages_missing: int):
        """Log dependency check results."""
        self.log_event(
            'check',
            f'Checked {component} dependencies',
            {
                'component': component,
                'found': packages_found,
                'missing': packages_missing
            }
        )

    def log_install(self, package_type: str, packages: list, success: bool):
        """Log package installation."""
        self.log_event(
            'install',
            f'{"Successfully installed" if success else "Failed to install"} {package_type} packages',
            {
                'package_type': package_type,
                'packages': packages,
                'success': success
            }
        )

    def log_error(self, message: str, error: Exception = None):
        """Log an error."""
        details = {'message': message}
        if error:
            details['error'] = str(error)
            details['error_type'] = type(error).__name__

        self.log_event('error', message, details)

    def log_complete(self, success: bool, voicemode_installed: bool):
        """Log installation completion."""
        self.log_event(
            'complete',
            'Installation completed' if success else 'Installation failed',
            {
                'success': success,
                'voicemode_installed': voicemode_installed
            }
        )

    def get_log_path(self) -> str:
        """Get the path to the log file."""
        return str(self.log_path)
