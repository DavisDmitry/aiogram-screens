import nox

nox.options.default_venv_backend = "uv"
nox.options.sessions = ["lint", "tests", "coverage"]

PYTHONS = ["3.11", "3.12", "3.13", "3.14"]
SOURCES = ["src", "tests", "noxfile.py"]


def sync(session: nox.Session, *groups: str) -> None:
    """Install the project and dependency groups from uv.lock into the session."""
    session.run_install(
        "uv",
        "sync",
        "--locked",
        "--no-default-groups",
        *(f"--group={group}" for group in groups),
        f"--python={session.virtualenv.location}",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )


@nox.session(name="format")
def format_(session: nox.Session) -> None:
    sync(session, "linters")
    session.run("ruff", "check", "--fix", *SOURCES)
    session.run("ruff", "format", *SOURCES)


@nox.session
def lint(session: nox.Session) -> None:
    sync(session, "linters", "tests")
    session.run("ruff", "check", *SOURCES)
    session.run("ruff", "format", "--check", "--diff", *SOURCES)
    session.run("mypy", *SOURCES)


@nox.session(python=PYTHONS)
def tests(session: nox.Session) -> None:
    sync(session, "tests")
    session.run(
        "pytest",
        "--cov",
        "--cov-report=",
        *session.posargs,
        env={"COVERAGE_FILE": f".coverage.{session.python}"},
    )


@nox.session
def coverage(session: nox.Session) -> None:
    sync(session, "tests")
    session.run("coverage", "combine")
    session.run("coverage", "report", "--show-missing")
