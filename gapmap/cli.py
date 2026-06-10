"""Phases 1 + 6 - GapMap CLI.

Commands (per the implementation plan):

    gapmap parse      - scan the repo, show files / LOC / dependencies
    gapmap audit      - top undocumented high-risk files (the MVP)
    gapmap ask        - explain why a file is risky
    gapmap generate   - draft an ADR for a file
    gapmap report     - write a self-contained HTML report
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from gapmap import __version__
from gapmap.analysis import RepoAnalysis, analyze
from gapmap.risk_engine import risk_level

app = typer.Typer(
    name="gapmap",
    help="Find the riskiest undocumented code in your repository.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

_LEVEL_STYLES = {"high": "bold red", "medium": "yellow", "low": "green"}

RepoOption = typer.Option(
    Path("."), "--repo", "-r", help="Path to the repository to scan.",
    exists=True, file_okay=False, resolve_path=True,
)


def _analyze(repo: Path) -> RepoAnalysis:
    with console.status("[bold cyan]Scanning repository...", spinner="dots"):
        analysis = analyze(repo)
    if not analysis.modules:
        console.print("[yellow]No Python files found in this repository.[/yellow]")
        raise typer.Exit(code=1)
    return analysis


def _resolve_or_exit(analysis: RepoAnalysis, target: str) -> str:
    key = analysis.resolve_target(target)
    if key is None:
        console.print(f"[bold red]Entity not found in repo:[/bold red] {target}")
        suggestions = [r.key for r in analysis.risks[:5]]
        if suggestions:
            console.print("Did you mean one of these?")
            for s in suggestions:
                console.print(f"  - {s}")
        raise typer.Exit(code=1)
    return key


def _level_cell(score: int, max_score: int) -> str:
    level = risk_level(score, max_score)
    return f"[{_LEVEL_STYLES[level]}]{level.upper()}[/{_LEVEL_STYLES[level]}]"


@app.callback()
def _version_callback() -> None:
    """GapMap - the documentation-debt auditor."""


# --------------------------------------------------------------------------- #
# parse
# --------------------------------------------------------------------------- #
@app.command()
def parse(repo: Path = RepoOption) -> None:
    """Scan the repo and show files, LOC, and import relationships."""
    analysis = _analyze(repo)

    entity_count = sum(len(info.entities) for info in analysis.modules.values())
    table = Table(
        title=f"Parsed {len(analysis.modules)} Python files, {entity_count} entities",
        header_style="bold cyan",
    )
    table.add_column("File", style="white", no_wrap=False)
    table.add_column("LOC", justify="right")
    table.add_column("Entities", justify="right")
    table.add_column("Imports", justify="right")
    table.add_column("Local dependencies")

    for rel, info in analysis.modules.items():
        deps = ", ".join(info.local_deps) if info.local_deps else "[dim]-[/dim]"
        table.add_row(
            rel, str(info.loc), str(len(info.entities)), str(len(info.imports)), deps
        )

    console.print(table)
    edges = analysis.graph.number_of_edges()
    console.print(
        f"\n[green]Entity call graph:[/green] {entity_count} entity nodes, "
        f"{edges} call edges across {len(analysis.modules)} files"
    )


# --------------------------------------------------------------------------- #
# audit
# --------------------------------------------------------------------------- #
@app.command()
def audit(
    repo: Path = RepoOption,
    top: int = typer.Option(10, "--top", "-n", help="How many entities to show."),
) -> None:
    """Show the top undocumented high-risk entities (the main MVP view)."""
    analysis = _analyze(repo)
    gaps = analysis.undocumented_risks()[:top]
    max_score = analysis.max_score()

    if not gaps:
        console.print(Panel(
            "[bold green]No undocumented load-bearing entities found.[/bold green]\n"
            "Every entity other code depends on is mentioned in your docs.",
            title="gapmap audit", border_style="green",
        ))
        return

    table = Table(
        title="Top Undocumented Risk Entities",
        header_style="bold cyan",
        title_style="bold white",
    )
    table.add_column("#", justify="right", style="dim")
    table.add_column("Entity", style="white")
    table.add_column("Type", justify="center")
    table.add_column("File")
    table.add_column("Called by", justify="right")
    table.add_column("LOC", justify="right")
    table.add_column("Risk score", justify="right", style="bold")
    table.add_column("Level", justify="center")
    table.add_column("Docs", justify="center")

    for i, risk in enumerate(gaps, start=1):
        table.add_row(
            str(i),
            risk.entity_name,
            risk.entity_type,
            risk.file,
            str(risk.incoming),
            str(risk.loc),
            f"{risk.score:,}",
            _level_cell(risk.score, max_score),
            "[red]Missing[/red]",
        )

    console.print(table)
    worst = gaps[0]
    console.print(
        f"\n[bold]Next step:[/bold] gapmap generate {worst.entity_name} "
        f"[dim](drafts the missing ADR for your #1 risk)[/dim]"
    )


# --------------------------------------------------------------------------- #
# ask
# --------------------------------------------------------------------------- #
@app.command()
def ask(
    target: str = typer.Argument(
        ..., help="Entity or file to ask about, e.g. route_payment"
    ),
    question: str = typer.Argument("why is this risky?", help="Your question."),
    repo: Path = RepoOption,
) -> None:
    """Ask why an entity is risky. Answers use only measured facts."""
    from gapmap.ask import build_answer

    analysis = _analyze(repo)
    key = _resolve_or_exit(analysis, target)
    risk = analysis.risk_for(key)
    label = f"{risk.entity_name} ({risk.file})" if risk else key
    answer = build_answer(analysis, key, question)

    console.print(Panel(
        answer,
        title=f"[bold]{label}[/bold] - {question}",
        border_style="cyan",
        padding=(1, 2),
    ))


# --------------------------------------------------------------------------- #
# generate
# --------------------------------------------------------------------------- #
@app.command()
def generate(
    target: str = typer.Argument(
        ..., help="Entity or file to document, e.g. route_payment"
    ),
    repo: Path = RepoOption,
) -> None:
    """Generate a draft ADR for an entity and save it under docs/adr/."""
    from gapmap.generator import write_adr

    analysis = _analyze(repo)
    key = _resolve_or_exit(analysis, target)

    with console.status("[bold cyan]Drafting ADR...", spinner="dots"):
        output = write_adr(analysis, key)

    console.print(Panel(
        f"ADR written to [bold]{output}[/bold]\n\n"
        "It is a [yellow]draft[/yellow]: confirm the inferred decision with "
        "the original authors before treating it as the source of truth.",
        title="[bold green]ADR generated[/bold green]",
        border_style="green",
    ))


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
@app.command()
def report(
    repo: Path = RepoOption,
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Where to write the HTML report."
    ),
) -> None:
    """Write a self-contained HTML report (gapmap-report.html)."""
    from gapmap.report import write_report

    analysis = _analyze(repo)
    with console.status("[bold cyan]Building report...", spinner="dots"):
        path = write_report(analysis, output)

    gaps = len(analysis.undocumented_risks())
    console.print(Panel(
        f"Report written to [bold]{path}[/bold]\n\n"
        f"Entities scanned: {len(analysis.entities)}  -  "
        f"Undocumented risks: {gaps}  -  "
        f"Doc coverage: {analysis.adr_coverage():.0%}",
        title="[bold green]Report ready[/bold green]",
        border_style="green",
    ))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
