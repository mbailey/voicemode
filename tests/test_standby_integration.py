"""Tests verifying the standby command has been removed.

The standby command was replaced by 'voicemode connect up' which has
proper VOICEMODE_CONNECT_ENABLED guard and the new connect architecture.
"""


class TestStandbyRemoved:
    """Verify the old standby command is gone."""

    def test_standby_command_not_registered(self):
        """standby command should not exist under connect group."""
        from click.testing import CliRunner
        from voice_mode.cli import connect

        runner = CliRunner()
        result = runner.invoke(connect, ["standby", "--help"])

        # Should fail because standby no longer exists
        assert result.exit_code != 0

    def test_up_command_exists(self):
        """'up' command should exist as the replacement."""
        from click.testing import CliRunner
        from voice_mode.cli import connect

        runner = CliRunner()
        result = runner.invoke(connect, ["up", "--help"])

        assert result.exit_code == 0
        assert "voicemode.dev" in result.output
