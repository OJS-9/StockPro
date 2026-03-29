"""
Pytest bootstrap: allow importing `src/app.py` without a local `.env`.

`app` fail-fast requires CLERK_* and FLASK_SECRET_KEY. CI sets these in the workflow;
developers with a real `.env` keep their values (setdefault).
"""


def pytest_configure(config):
    import os

    os.environ.setdefault("FLASK_SECRET_KEY", "pytest-local-flask-secret")
    os.environ.setdefault("CLERK_SECRET_KEY", "sk_test_pytest")
    os.environ.setdefault(
        "CLERK_JWT_KEY",
        "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE\n-----END PUBLIC KEY-----",
    )
    os.environ.setdefault("CLERK_PUBLISHABLE_KEY", "pk_test_pytest")
