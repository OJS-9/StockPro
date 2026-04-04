"""SSE chat error string helper (Phase 1.7)."""


def test_sse_user_facing_error_empty_message():
    import app as app_module

    assert app_module.sse_user_facing_error(RuntimeError("")) == (
        "Something went wrong. Please try again."
    )


def test_sse_user_facing_error_truncates():
    import app as app_module

    long_msg = "x" * 600
    out = app_module.sse_user_facing_error(RuntimeError(long_msg))
    assert len(out) == 500
    assert out.endswith("...")


def test_sse_user_facing_error_passes_through_short():
    import app as app_module

    assert app_module.sse_user_facing_error(ValueError("Bad ticker")) == "Bad ticker"
