"""Signature-parity guard for the converse() / _converse_core() split (VM-1961, do-001/do-002).

``converse()`` is a thin ``@mcp.tool()`` wrapper around the unwrapped
``_converse_core()`` coroutine, so that a single choke point (the wrapper)
can uniformly touch every return path (e.g. appending a widgets segment,
VM-1961 do-002) without enumerating ~28 individual return sites inside the
core.

This test is the safety net for that split: it fails loudly the moment the
wrapper's parameter list drifts from the core's beyond the one expected
extra param, which is a much safer property than "did we remember to
forward every parameter by keyword."

As of do-002, the wrapper adds exactly one new wrapper-only parameter,
``time_in_response`` (the time-widget toggle), on top of every core param
forwarded unchanged.
"""

import inspect

from voice_mode.tools.converse import converse, _converse_core

# do-002: the wrapper's one deliberate extra parameter beyond the core's.
_WRAPPER_ONLY_PARAMS = ("time_in_response",)


def _wrapper_fn():
    """The underlying coroutine behind the converse MCP tool (unwraps FastMCP)."""
    return getattr(converse, "fn", converse)


def test_wrapper_and_core_have_identical_signatures():
    """converse() forwards every core parameter by keyword, adding only time_in_response."""
    core_params = inspect.signature(_converse_core).parameters
    wrapper_params = inspect.signature(_wrapper_fn()).parameters

    assert list(wrapper_params.keys()) == list(core_params.keys()) + list(_WRAPPER_ONLY_PARAMS), (
        "converse() wrapper's parameter list has drifted from _converse_core()'s "
        f"plus the expected wrapper-only params {_WRAPPER_ONLY_PARAMS!r}. Keep them in sync."
    )

    for name, core_param in core_params.items():
        wrapper_param = wrapper_params[name]
        assert wrapper_param.default == core_param.default, (
            f"Default for {name!r} differs between wrapper ({wrapper_param.default!r}) "
            f"and core ({core_param.default!r})"
        )
        # Compare by repr rather than `==`: a couple of params (e.g. `turns`)
        # are `Annotated[..., pydantic.Field(...)]`, and pydantic's FieldInfo
        # doesn't define value equality across two separately-constructed
        # instances (core and wrapper each call `Field(...)` once), so `==`
        # is a false negative here even when the two annotations are
        # textually/structurally identical. repr() captures that identity.
        assert repr(wrapper_param.annotation) == repr(core_param.annotation), (
            f"Annotation for {name!r} differs between wrapper "
            f"({wrapper_param.annotation!r}) and core ({core_param.annotation!r})"
        )


def test_wrapper_only_params_are_optional_with_none_default():
    """Wrapper-only params (time_in_response) must be opt-in: Optional, default None."""
    wrapper_params = inspect.signature(_wrapper_fn()).parameters
    for name in _WRAPPER_ONLY_PARAMS:
        assert name in wrapper_params, f"Expected wrapper-only param {name!r} not found"
        assert wrapper_params[name].default is None, (
            f"{name!r} must default to None (opt-in, falls back to config global)"
        )


def test_wrapper_return_type_matches_core():
    core_sig = inspect.signature(_converse_core)
    wrapper_sig = inspect.signature(_wrapper_fn())
    assert wrapper_sig.return_annotation == core_sig.return_annotation
