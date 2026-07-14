"""Signature-parity guard for the converse() / _converse_core() split (VM-1961, do-001).

``converse()`` is a thin ``@mcp.tool()`` wrapper around the unwrapped
``_converse_core()`` coroutine, so that a single choke point (the wrapper)
can uniformly touch every return path (e.g. appending a widgets segment,
VM-1961 do-002) without enumerating ~28 individual return sites inside the
core.

This test is the safety net for that split: it fails loudly the moment the
wrapper's parameter list drifts from the core's, which is a much safer
property than "did we remember to forward every parameter by keyword."

At this slice (do-001) the wrapper is a pure pass-through with *zero* new
parameters, so wrapper params must equal core params exactly. A later slice
(do-002) is expected to add exactly one new wrapper-only parameter
(``time_in_response``) and will update this test accordingly.
"""

import inspect

from voice_mode.tools.converse import converse, _converse_core


def _wrapper_fn():
    """The underlying coroutine behind the converse MCP tool (unwraps FastMCP)."""
    return getattr(converse, "fn", converse)


def test_wrapper_and_core_have_identical_signatures():
    """do-001: converse() forwards every parameter by keyword, adding none."""
    core_params = inspect.signature(_converse_core).parameters
    wrapper_params = inspect.signature(_wrapper_fn()).parameters

    assert list(wrapper_params.keys()) == list(core_params.keys()), (
        "converse() wrapper's parameter list has drifted from _converse_core()'s. "
        "Keep them in sync (or update this test if do-002's time_in_response "
        "param has landed)."
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


def test_wrapper_return_type_matches_core():
    core_sig = inspect.signature(_converse_core)
    wrapper_sig = inspect.signature(_wrapper_fn())
    assert wrapper_sig.return_annotation == core_sig.return_annotation
