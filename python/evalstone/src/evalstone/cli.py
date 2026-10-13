"""The ``evalstone`` command."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from evalstone import __version__
from evalstone.config import CONFIG_FILENAME, Config
from evalstone.run import Run, compare

app = typer.Typer(
    name="evalstone",
    help="The plug-and-play evals layer for LLM-based projects.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err = Console(stderr=True)

ConfigOpt = typer.Option("evalstone.yaml", "--config", "-c", help="Path to evalstone.yaml")
ReportOpt = typer.Option(None, "--report", "-r", help="Where to write the JSON report")
BaselineOpt = typer.Option(
    None, "--baseline", "-b", help="A previous report to gate regressions against"
)
FailuresOpt = typer.Option(10, "--failures", help="How many failing results to print")
DirArg = typer.Argument(Path("."), help="Where to create evalstone.yaml and evals/")


def _load(config: str) -> Config:
    try:
        return Config.load(config)
    except FileNotFoundError as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from None


def _run_table(run: Run) -> Table:
    t = Table(title=f"{run.suite} · {run.dataset}@{run.dataset_hash[:12]} · run {run.id}")
    t.add_column("check")
    for col in ("n", "pass", "mean", "err", "cost"):
        t.add_column(col, justify="right")
    for c in run.summary.per_check:
        t.add_row(
            c.key,
            str(c.n),
            f"{c.pass_rate:.1%}",
            f"{c.mean_score:.3f}",
            str(c.errors),
            f"${c.cost_usd:.4f}",
        )
    s = run.summary
    t.add_section()
    t.add_row(
        "total",
        str(s.results),
        f"{s.pass_rate:.1%}",
        f"{s.mean_score:.3f}",
        str(s.errors),
        f"${s.cost_usd:.4f}",
    )
    return t


def _print_failures(run: Run, limit: int) -> None:
    failures = run.failures()
    if not failures:
        return
    suffix = f", first {limit}:" if len(failures) > limit else ":"
    console.print(f"\n[bold]{len(failures)} failing result(s)[/bold]{suffix}")
    for r in failures[:limit]:
        flag = "[red]error[/red]" if r.score.error else "[yellow]fail[/yellow]"
        console.print(f"  {flag} {r.sample_id} · {r.check_key} · {r.score.reason}")


def _print_gate(run: Run) -> None:
    if run.gate_passed is None:
        return
    verdict = "[green]PASSED[/green]" if run.gate_passed else "[red]FAILED[/red]"
    console.print(f"\n[bold]gate[/bold] {verdict}")
    for line in run.gate_lines:
        colour = {"PASS": "green", "FAIL": "red", "SKIP": "dim", "WARN": "yellow"}.get(line[:4], "")
        console.print(f"  [{colour}]{line}[/{colour}]" if colour else f"  {line}")


@app.callback(invoke_without_command=True)
def _version_callback(
    version: bool = typer.Option(
        False, "--version", "-V", help="Print the version and exit", is_eager=True
    ),
) -> None:
    if version:
        console.print(f"evalstone {__version__}")
        raise typer.Exit()


@app.command()
def run(
    suite: str = typer.Argument(..., help="Suite name from evalstone.yaml"),
    config: str = ConfigOpt,
    report: Path | None = ReportOpt,
    baseline: Path | None = BaselineOpt,
    failures: int = FailuresOpt,
    strict: bool = typer.Option(False, "--strict", help="Exit 1 when the gate fails"),
) -> None:
    """Run a suite, print the table, write the JSON report."""
    cfg = _load(config)
    try:
        s, target = cfg.suite(suite)
    except (KeyError, ValueError, ImportError, AttributeError) as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from None
    base = Run.from_json(baseline) if baseline else None
    with console.status(f"running {suite} over {len(s.dataset)} samples…"):
        result = s.run(target, baseline=base, trigger="cli")
    console.print(_run_table(result))
    _print_failures(result, failures)
    _print_gate(result)
    out = report or (cfg.root / cfg.report)
    result.to_json(out)
    console.print(f"\nreport → {out}")
    if strict and result.gate_passed is False:
        raise typer.Exit(1)


@app.command()
def gate(
    suite: str = typer.Argument(..., help="Suite name from evalstone.yaml"),
    config: str = ConfigOpt,
    report: Path | None = ReportOpt,
    baseline: Path | None = BaselineOpt,
) -> None:
    """Run a suite and exit 1 if its gate fails (for CI)."""
    run(suite=suite, config=config, report=report, baseline=baseline, failures=10, strict=True)


@app.command("compare")
def compare_cmd(a: Path, b: Path) -> None:
    """Diff two JSON reports: regressions, improvements, metric deltas."""
    cmp = compare(Run.from_json(a), Run.from_json(b))
    console.print(cmp.table())
    raise typer.Exit(1 if cmp.regressions else 0)


@app.command()
def show(report: Path, failures: int = FailuresOpt) -> None:
    """Print a saved report."""
    r = Run.from_json(report)
    console.print(_run_table(r))
    _print_failures(r, failures)
    _print_gate(r)


@app.command("list")
def list_cmd(config: str = ConfigOpt) -> None:
    """List datasets, checks and suites in the config."""
    cfg = _load(config)
    cfg.activate()
    console.print(f"[bold]{cfg.project}[/bold] ({cfg.root / CONFIG_FILENAME})")
    console.print("datasets: " + ", ".join(f"{k} → {v}" for k, v in cfg.datasets.items()))
    console.print("checks:   " + ", ".join(f"{k} ({v.get('type')})" for k, v in cfg.checks.items()))
    from evalstone.checks import registry

    if registry.keys():
        console.print("registered: " + ", ".join(registry.keys()))
    for name, s in cfg.suites.items():
        console.print(
            f"suite {name}: dataset={s.dataset} target={s.target.get('kind')} checks={s.checks}"
        )


INIT_YAML = """project: {project}
imports: [evals.checks]
datasets:
  golden: evals/golden.jsonl
checks:
  must_include: {{ type: contains }}
  short: {{ type: length, max_words: 120 }}
suites:
  nightly:
    dataset: golden
    target: {{ kind: recorded, path: evals/outputs.jsonl }}
    checks: [must_include, short, no_apology]
    gate: {{ min_pass_rate: 0.9 }}
"""

INIT_CHECKS = '''"""Project checks — plain functions registered with @check."""

from evalstone import check


@check("no_apology")
def no_apology(sample, output):
    """Fails when the answer apologises instead of answering."""
    return "sorry" not in output.text.lower()
'''

INIT_SAMPLES = [
    {
        "id": "returns",
        "input": "Can I return a sale item?",
        "expected": {"must_include": ["30 days"]},
        "tags": ["refund"],
    },
    {
        "id": "shipping",
        "input": "How long does shipping take?",
        "expected": {"must_include": ["3-5"]},
        "tags": ["shipping"],
    },
]
INIT_OUTPUTS = [
    {"id": "returns", "output": "Yes — sale items can be returned within 30 days with a receipt."},
    {"id": "shipping", "output": "Standard shipping takes 3-5 business days."},
]


@app.command()
def init(
    directory: Path = DirArg,
    project: str = typer.Option(None, "--project", "-p"),
) -> None:
    """Create a starter evalstone.yaml, a golden set, recorded outputs and a custom check."""
    directory.mkdir(parents=True, exist_ok=True)
    cfg = directory / CONFIG_FILENAME
    if cfg.exists():
        err.print(f"[red]{cfg} already exists[/red]")
        raise typer.Exit(2)
    evals = directory / "evals"
    evals.mkdir(exist_ok=True)
    cfg.write_text(INIT_YAML.format(project=project or directory.resolve().name), encoding="utf-8")
    (evals / "checks.py").write_text(INIT_CHECKS, encoding="utf-8")
    (evals / "__init__.py").write_text("", encoding="utf-8")
    samples = "".join(json.dumps(s) + "\n" for s in INIT_SAMPLES)
    outputs = "".join(json.dumps(o) + "\n" for o in INIT_OUTPUTS)
    (evals / "golden.jsonl").write_text(samples, encoding="utf-8")
    (evals / "outputs.jsonl").write_text(outputs, encoding="utf-8")
    console.print(f"created {cfg}, evals/golden.jsonl, evals/outputs.jsonl, evals/checks.py")
    console.print("next: [bold]evalstone run nightly[/bold]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
