"""Bash completion scripts bundled with the voicemode package."""

from importlib.resources import files


def get_completion_path(name: str) -> str:
    """Return the filesystem path to a bundled completion script.

    Args:
        name: Filename of the completion script (e.g. ``"sayas.bash"``).

    Returns:
        Absolute path to the completion file.

    Raises:
        FileNotFoundError: If the named completion script does not exist.
    """
    resource = files(__package__).joinpath(name)
    # importlib.resources may return a Traversable; as_posix gives the path
    path = str(resource)
    return path
