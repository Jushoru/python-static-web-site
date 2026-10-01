"""Cross-platform commands; Nox manages a reusable environment per session."""

import sys

import nox

nox.options.sessions = ["build"]


def install_dependencies(session):
    # Exact versions are shared by local runs and the future CI workflow.
    if session.venv_backend == "none":
        session.log("Using dependencies installed before Nox (no virtualenv).")
        return
    session.install("-r", "requirements.txt")


def run_python(session, *arguments):
    # Passthrough mode must use Nox's interpreter, not a different Python on PATH.
    executable = sys.executable if session.venv_backend == "none" else "python"
    session.run(executable, *arguments)


@nox.session(reuse_venv=True, venv_backend="virtualenv")
def build(session):
    """Prepare results using the cache and build the site in strict mode."""
    install_dependencies(session)
    run_python(session, "-m", "mkdocs", "build", "--strict", *session.posargs)


@nox.session(reuse_venv=True, venv_backend="virtualenv")
def serve(session):
    """Open the local development server (stop with Ctrl+C)."""
    install_dependencies(session)
    run_python(session, "-m", "mkdocs", "serve", *session.posargs)


@nox.session(name="cache-benchmark", reuse_venv=True, venv_backend="virtualenv")
def cache_benchmark(session):
    """Measure cached and uncached report preparation, excluding installation."""
    install_dependencies(session)
    run_python(session, "scripts/benchmark_cache.py", *session.posargs)


@nox.session(reuse_venv=True, venv_backend="virtualenv")
def check(session):
    """Check cache invalidation, restoration and data validation."""
    install_dependencies(session)
    run_python(session, "-m", "unittest", "discover", "-s", "tests", "-v")
