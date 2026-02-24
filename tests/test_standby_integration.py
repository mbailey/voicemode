"""Tests verifying the standby and connect up/down commands have been removed.

The standalone daemon model (standby → connect up) was replaced by
agent-driven presence via the connect_status MCP tool (VM-824).
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


class TestConnectUpDownRemoved:
    """Verify connect up and down are gone (VM-824)."""

    def test_up_command_not_registered(self):
        from click.testing import CliRunner
        from voice_mode.cli import connect

        runner = CliRunner()
        result = runner.invoke(connect, ["up", "--help"])
        assert result.exit_code != 0

    def test_down_command_not_registered(self):
        from click.testing import CliRunner
        from voice_mode.cli import connect

        runner = CliRunner()
        result = runner.invoke(connect, ["down", "--help"])
        assert result.exit_code != 0
