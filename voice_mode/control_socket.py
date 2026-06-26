"""Unix-domain-socket control listener for VoiceMode (VM-1676).

This is the *transport* layer of the control channel. It owns a Unix domain
socket (default ``~/.voicemode/control.sock``), accepts local connections, reads
newline-delimited JSON command lines, and drives the thread-safe ``ControlState``
in :mod:`voice_mode.control_channel`. An external trigger -- a Stream Deck press,
a media key, a spoken keyword, or any local process -- can therefore pause /
resume / stop an in-flight TTS utterance *without* going through the MCP protocol
stream and *without* pressing ESC.

The listener is deliberately **decoupled from playback and from how commands are
shaped**: it only knows "read a line, parse it, apply it to a ``ControlState``".
The parse/validate lives in :mod:`voice_mode.control_channel`, so an HTTP (or any
other) listener could replace this file later without touching playback or the
state machine.

Lifecycle (VM-1676 design): bind only while an audio operation is active, and
unlink + close on exit, so only the currently-speaking server owns the single
well-known socket (the conch already serializes who-is-talking across processes).
A crashed server can leave a stale socket file behind, so :meth:`start` does
unlink-then-bind. The module-level :func:`start_control_listener` /
:func:`stop_control_listener` are the config-gated seam the ``converse`` audio op
calls into (wired in a later feature).

Threading model: a daemon *accept* thread loops on ``accept()`` (with a short
timeout so :meth:`stop` is responsive) and hands each connection to a short-lived
daemon *handler* thread. ``ControlState`` is itself thread-safe, so concurrent
handlers are fine and one slow/held client can never wedge the channel.
"""

import json
import logging
import os
import socket
import stat
import struct
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Set

from voice_mode import config
from voice_mode.control_channel import (
    MAX_LINE_BYTES,
    ControlCommandError,
    ControlState,
    get_control_state,
    parse_command,
)

logger = logging.getLogger("voicemode.control_socket")

# How long accept()/recv() block before re-checking the stop flag. Bounds
# teardown latency (stop() returns within roughly this long) without
# busy-spinning the CPU while idle.
_POLL_TIMEOUT = 0.25

# Max bytes read per recv. Control lines are tiny JSON; this is just a ceiling.
_RECV_SIZE = 4096

# Hardening caps (F7 / VM-1697): the channel only ever needs sub-second command
# bursts, so bound concurrent handlers and each connection's total lifetime to
# stop a local process exhausting threads/fds or holding connections open.
_MAX_HANDLERS = 8
_CONN_MAX_LIFETIME = 10.0


def _peer_uid(conn: socket.socket) -> Optional[int]:
    """Best-effort UID of the connected peer, or ``None`` if it can't be read.

    F3 (VM-1694): the socket itself authenticates nobody, so we check the peer's
    credentials on accept and reject anyone who isn't this same user. Uses
    ``SO_PEERCRED`` on Linux and ``LOCAL_PEERCRED`` (struct xucred) on macOS/BSD.
    Returns ``None`` when the platform/recv can't give us a UID -- the caller
    fails *open* in that case (logged), since this is defence-in-depth on top of
    the 0700 dir + off-by-default gate, not the sole guarantee.
    """
    try:
        if sys.platform.startswith("linux"):
            creds = conn.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
            )
            _pid, uid, _gid = struct.unpack("3i", creds)
            return uid
        if sys.platform == "darwin" or "bsd" in sys.platform:
            # struct xucred { u_int cr_version; uid_t cr_uid; ... }; uid at +4.
            SOL_LOCAL = 0
            LOCAL_PEERCRED = 0x001
            xucred = conn.getsockopt(SOL_LOCAL, LOCAL_PEERCRED, 4 + 4 + 2 + 16 * 4)
            _version, uid = struct.unpack("II", xucred[:8])
            return uid
    except OSError:
        return None
    return None


class ControlSocketListener:
    """A Unix-domain-socket server that drives a :class:`ControlState`.

    Pure mechanism -- it does not consult ``VOICEMODE_CONTROL_CHANNEL_ENABLED``
    (that gate lives in :func:`start_control_listener`) and it does not touch
    playback. Construct it with an explicit ``socket_path`` / ``control_state``
    in tests; in production it defaults to the configured socket path and the
    process-wide control-state singleton.

    Usage::

        listener = ControlSocketListener()
        listener.start()   # binds + spawns the accept thread
        ...                # external triggers send JSON lines, state flips
        listener.stop()    # joins threads, closes + unlinks the socket
    """

    def __init__(
        self,
        socket_path: Optional[os.PathLike] = None,
        control_state: Optional[ControlState] = None,
    ) -> None:
        self._socket_path = (
            Path(socket_path)
            if socket_path is not None
            else Path(config.CONTROL_SOCKET_PATH)
        )
        self._state = control_state if control_state is not None else get_control_state()

        self._server: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

        # Guards start/stop and the server/accept-thread handles.
        self._lifecycle_lock = threading.Lock()
        # Tracks in-flight per-connection handler threads for a clean join on stop.
        self._handlers: Set[threading.Thread] = set()
        self._handlers_lock = threading.Lock()

    # --- properties ------------------------------------------------------

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    @property
    def is_running(self) -> bool:
        t = self._accept_thread
        return t is not None and t.is_alive()

    # --- lifecycle -------------------------------------------------------

    def start(self) -> None:
        """Bind the socket and start accepting connections.

        Idempotent: a no-op if already running. Does unlink-then-bind so a stale
        socket file left by a crashed server doesn't block the bind. Raises
        ``OSError`` if the socket can't be bound (the caller decides whether a
        failed control channel should be fatal -- :func:`start_control_listener`
        treats it as non-fatal).
        """
        with self._lifecycle_lock:
            if self.is_running:
                logger.debug("control listener already running on %s", self._socket_path)
                return
            self._stop.clear()
            self._server = self._bind()
            self._accept_thread = threading.Thread(
                target=self._serve,
                name="voicemode-control-listener",
                daemon=True,
            )
            self._accept_thread.start()
            logger.info("control listener bound to %s", self._socket_path)

    def stop(self) -> None:
        """Stop accepting, join the threads, then close + unlink the socket.

        Safe to call when not running and safe to call more than once. Tears the
        socket file down so the next ``start`` (this server or another) starts
        clean.
        """
        with self._lifecycle_lock:
            self._stop.set()
            accept_thread = self._accept_thread
            server = self._server
            self._accept_thread = None
            self._server = None

        # Closing the listening socket unblocks a blocked accept() promptly.
        if server is not None:
            try:
                server.close()
            except OSError:
                logger.debug("error closing control socket", exc_info=True)

        if accept_thread is not None and accept_thread is not threading.current_thread():
            accept_thread.join(timeout=2.0)

        # Best-effort join of any in-flight connection handlers (they bail within
        # _POLL_TIMEOUT of the stop flag being set).
        with self._handlers_lock:
            handlers = list(self._handlers)
        for handler in handlers:
            if handler is not threading.current_thread():
                handler.join(timeout=1.0)

        self._unlink_socket()
        logger.debug("control listener stopped; %s unlinked", self._socket_path)

    # --- internals -------------------------------------------------------

    def _bind(self) -> socket.socket:
        """Create, bind, and listen on the Unix socket (unlink-then-bind).

        F2 (VM-1694): on macOS/BSD a socket file's own ``0600`` is not reliably
        enforced on ``connect()`` -- access is gated by the *directory*. So we
        lock the parent dir to ``0700`` and ``umask(0o077)`` across the bind to
        close the chmod-after-bind TOCTOU window. The real, portable enforcement
        is the F3 peer-credential check on accept; these are defence in depth.
        """
        path = self._socket_path
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(str(path.parent), 0o700)
        except OSError:
            logger.debug("could not chmod control socket dir %s", path.parent, exc_info=True)
        # Stale-socket recovery: a crashed server can leave the file behind,
        # which would make bind() fail with EADDRINUSE. Remove it first (safely).
        self._unlink_socket()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old_umask = os.umask(0o077)  # socket is created owner-only, no race
        try:
            server.bind(str(path))
            server.listen(8)
            server.settimeout(_POLL_TIMEOUT)
        except OSError:
            server.close()
            raise
        finally:
            os.umask(old_umask)

        # Belt-and-braces: restrict the socket file too (best effort -- not all
        # platforms enforce socket-file perms; the dir + peer-cred check do).
        try:
            os.chmod(str(path), 0o600)
        except OSError:
            logger.debug("could not chmod control socket %s", path, exc_info=True)

        return server

    def _unlink_socket(self) -> None:
        """Remove the socket file -- but only if it's actually our own socket.

        F6 (VM-1697): the old unconditional ``os.unlink`` would happily delete a
        regular file, a symlink, or another user's node sitting at the path
        (squatting / interception risk). ``lstat`` first (no symlink follow) and
        refuse unless it's a socket owned by us.
        """
        path = str(self._socket_path)
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            return
        except OSError:
            logger.warning("could not stat control socket %s", path, exc_info=True)
            return
        if not stat.S_ISSOCK(st.st_mode):
            logger.warning("refusing to unlink non-socket at control path %s", path)
            return
        if st.st_uid != os.getuid():
            logger.warning(
                "refusing to unlink control socket %s owned by uid %s (not %s)",
                path, st.st_uid, os.getuid(),
            )
            return
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except OSError:
            logger.warning("could not remove control socket %s", path, exc_info=True)

    def _serve(self) -> None:
        """Accept loop: hand each connection to a handler thread until stopped."""
        server = self._server
        if server is None:  # pragma: no cover -- start() always sets it first
            return
        try:
            while not self._stop.is_set():
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    # Expected when stop() closes the socket out from under us.
                    if self._stop.is_set():
                        break
                    logger.warning("control listener accept failed", exc_info=True)
                    continue

                # F3 (VM-1694): authenticate the peer -- only this same user may
                # drive the channel. Reject a definite mismatch; fail open (with a
                # debug note) only when the platform can't tell us the UID.
                peer = _peer_uid(conn)
                if peer is not None and peer != os.getuid():
                    logger.warning(
                        "control listener: rejecting connection from uid %s (not %s)",
                        peer, os.getuid(),
                    )
                    self._close_quietly(conn)
                    continue
                if peer is None:
                    logger.debug("control listener: peer UID unavailable; allowing (defence-in-depth)")

                # F7 (VM-1697): cap concurrent handlers so a flood of connections
                # can't exhaust threads. Drop the newest over the cap.
                with self._handlers_lock:
                    over_cap = len(self._handlers) >= _MAX_HANDLERS
                if over_cap:
                    logger.warning(
                        "control listener: handler cap (%d) reached; dropping connection",
                        _MAX_HANDLERS,
                    )
                    self._close_quietly(conn)
                    continue

                handler = threading.Thread(
                    target=self._handle_connection,
                    args=(conn,),
                    name="voicemode-control-conn",
                    daemon=True,
                )
                with self._handlers_lock:
                    self._handlers.add(handler)
                handler.start()
        finally:
            logger.debug("control listener accept loop exiting (%s)", self._socket_path)

    @staticmethod
    def _close_quietly(conn: socket.socket) -> None:
        try:
            conn.close()
        except OSError:
            pass

    def _handle_connection(self, conn: socket.socket) -> None:
        """Read newline-delimited JSON lines from one client and dispatch each."""
        try:
            conn.settimeout(_POLL_TIMEOUT)
            deadline = time.monotonic() + _CONN_MAX_LIFETIME
            buffer = b""
            while not self._stop.is_set():
                # F7 (VM-1697): bound total connection lifetime -- the channel
                # only needs quick command bursts, so a client that lingers (or a
                # slow-loris hold) is dropped rather than tying up a handler.
                if time.monotonic() > deadline:
                    logger.debug("control listener: connection exceeded max lifetime; closing")
                    break
                try:
                    chunk = conn.recv(_RECV_SIZE)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    # client closed (EOF): tolerate a final newline-less line.
                    if buffer.strip() and len(buffer) <= MAX_LINE_BYTES:
                        self._dispatch(buffer)
                    break
                buffer += chunk
                # F5 (VM-1694): cap the unparsed buffer so a connection that never
                # sends a newline can't grow it without bound (memory exhaustion).
                if len(buffer) > MAX_LINE_BYTES:
                    logger.warning(
                        "control listener: line exceeded %d bytes; dropping connection",
                        MAX_LINE_BYTES,
                    )
                    break
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    self._dispatch(line)
        except Exception:  # never let a bad client take down the handler
            logger.warning("control listener connection error", exc_info=True)
        finally:
            self._close_quietly(conn)
            with self._handlers_lock:
                self._handlers.discard(threading.current_thread())

    def _dispatch(self, raw: bytes) -> None:
        """Parse one raw line and apply it to the control state.

        Malformed / unknown input is logged and ignored -- a bad line must never
        crash the listener or the server.
        """
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning("control listener: ignoring non-UTF-8 line")
            return
        if not text.strip():
            return
        try:
            command = parse_command(text)
        except ControlCommandError as exc:
            logger.warning("control listener: ignoring malformed command: %s", exc)
            return
        try:
            command.apply_to(self._state)
            logger.info("control command applied: %s", command.command)
        except Exception:  # defensive -- apply_to shouldn't raise for valid commands
            logger.warning("control listener: failed to apply command", exc_info=True)


# --- Process-wide listener + config-gated seam ----------------------------
#
# These give the converse audio op (wired in a later feature) a one-line,
# config-respecting way to bring the channel up/down around an utterance, and
# are the consumers of VOICEMODE_CONTROL_CHANNEL_ENABLED / VOICEMODE_CONTROL_SOCKET.

_listener: Optional[ControlSocketListener] = None
_listener_lock = threading.Lock()


def get_control_listener() -> ControlSocketListener:
    """Return the process-wide :class:`ControlSocketListener` (created lazily)."""
    global _listener
    if _listener is None:
        with _listener_lock:
            if _listener is None:
                _listener = ControlSocketListener()
    return _listener


def start_control_listener() -> Optional[ControlSocketListener]:
    """Start the shared control listener iff the channel is enabled.

    Returns the listener when started (or already running), or ``None`` when the
    channel is disabled. A bind failure is treated as **non-fatal** -- the
    control channel is a convenience, so it's logged and swallowed rather than
    breaking voice playback.
    """
    if not config.CONTROL_CHANNEL_ENABLED:
        return None
    listener = get_control_listener()
    try:
        listener.start()
    except OSError:
        logger.warning(
            "control channel enabled but listener failed to start on %s; "
            "continuing without it",
            listener.socket_path,
            exc_info=True,
        )
        return None
    return listener


def stop_control_listener() -> None:
    """Stop the shared control listener if one exists. Safe to call unconditionally."""
    listener = _listener
    if listener is not None:
        listener.stop()


# --- Client: send one command to the control socket -----------------------
#
# The other end of the transport. The ``voicemode control`` CLI, a Stream Deck
# button, a media-key handler, or a spoken-keyword listener all funnel through
# here -- a *second local process* driving an in-flight utterance, which is what
# proves the channel is reusable (VM-1676 success criterion 2). Kept beside the
# listener so both ends of the Unix-socket transport live together; the command
# schema is still owned by control_channel.parse_command (used to validate
# below before anything goes on the wire).


def send_control_command(
    command: str,
    message: Optional[str] = None,
    hint: Optional[str] = None,
    socket_path: Optional[os.PathLike] = None,
    timeout: float = 2.0,
) -> None:
    """Connect to the control socket and write one newline-delimited JSON command.

    ``command`` must be ``pause`` / ``resume`` / ``stop``; ``message`` and
    ``hint`` are carried for ``stop`` (they feed the normal ``converse`` return
    string -- e.g. hint ``switch-to-text``). The payload is validated against the
    same schema the listener enforces (:func:`parse_command`) *before* anything
    is sent, so a bad command raises here rather than being silently dropped
    server-side.

    Raises:
        ControlCommandError: the command / message / hint don't satisfy the schema.
        FileNotFoundError: no socket at ``socket_path`` -- nothing is listening
            (the server isn't speaking, or the control channel is disabled).
        ConnectionRefusedError: a (stale) socket file exists but no server is
            accepting on it.
        OSError: any other socket failure (e.g. the connection/send times out).
    """
    payload = {"command": command}
    if message is not None:
        payload["message"] = message
    if hint is not None:
        payload["hint"] = hint
    line = json.dumps(payload)

    # Validate locally against the listener's own schema (single source of
    # truth), so callers fail fast on a bad command instead of having it dropped.
    parse_command(line)

    path = (
        Path(socket_path)
        if socket_path is not None
        else Path(config.CONTROL_SOCKET_PATH)
    )
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(path))
        client.sendall((line + "\n").encode("utf-8"))
    logger.debug("sent control command %s to %s", command, path)
