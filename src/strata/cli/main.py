"""Main Typer CLI entrypoint for Strata."""

from __future__ import annotations

import typer

from strata.cli.benchmark_cmd import benchmark_command
from strata.cli.compare_cmd import compare_command
from strata.cli.inspect_cmd import inspect_command
from strata.cli.run_cmd import run_command
from strata.cli.validate_cmd import validate_command
from strata.cli.verify_cmd import verify_command

app = typer.Typer(
    name="strata",
    help="Strata: Distributed Systems Engineering and Fault-Injection Framework",
    no_args_is_help=True,
    add_completion=False,
)

# Register implemented CLI commands
app.command(name="validate", help="Validate an experiment specification against the Strata schema.")(
    validate_command
)
app.command(name="run", help="Execute an experiment under deterministic discrete-event simulation.")(
    run_command
)
app.command(name="inspect", help="Inspect execution details, invariants, and event history for a run.")(
    inspect_command
)
app.command(name="verify", help="Verify cryptographic integrity of experiment artifacts against manifest.")(
    verify_command
)
app.command(name="compare", help="Compare two completed experiment runs and compute differential analysis.")(
    compare_command
)
app.command(name="benchmark", help="Benchmark performance, throughput, and speedup across multiple experiment trials.")(
    benchmark_command
)

if __name__ == "__main__":
    app()
