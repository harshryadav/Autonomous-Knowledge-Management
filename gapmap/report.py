"""Phase 9 - HTML report.

`gapmap report` writes a self-contained `gapmap-report.html`
(no external assets, opens offline) showing: files scanned, top
undocumented risk files, the highest-risk file, ADR coverage, a simple
dependency map of the biggest hubs, and recommended next actions.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import List

from gapmap.analysis import RepoAnalysis
from gapmap.risk_engine import FileRisk, risk_level

REPORT_NAME = "gapmap-report.html"

_LEVEL_COLORS = {"high": "#f87171", "medium": "#fbbf24", "low": "#34d399"}


def write_report(analysis: RepoAnalysis, output: str | Path | None = None) -> Path:
    path = Path(output) if output else analysis.root / REPORT_NAME
    path.write_text(build_html(analysis), encoding="utf-8")
    return path


def build_html(analysis: RepoAnalysis) -> str:
    total = len(analysis.modules)
    bearing = analysis.load_bearing()
    gaps = analysis.undocumented_risks()
    coverage = analysis.adr_coverage()
    top = analysis.risks[0] if analysis.risks and analysis.risks[0].score > 0 else None
    max_score = analysis.max_score()

    rows = "\n".join(
        _risk_row(i, r, analysis, max_score) for i, r in enumerate(gaps[:10], 1)
    ) or '<tr><td colspan="6" class="empty">No undocumented load-bearing files found.</td></tr>'

    hubs = sorted(bearing, key=lambda r: -r.incoming)[:5]
    dep_map = "\n".join(_hub_block(r, analysis) for r in hubs) or \
        '<p class="empty">No import relationships detected.</p>'

    actions = "\n".join(f"<li>{html.escape(a)}</li>" for a in _actions(analysis, gaps))

    top_card = (
        f'{html.escape(top.path)}<span class="sub">score {top.score:,}</span>'
        if top else 'none<span class="sub">no load-bearing files</span>'
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GapMap Report - {html.escape(analysis.root.name)}</title>
<style>
  :root {{
    --bg: #0f172a; --panel: #1e293b; --line: #334155;
    --text: #e2e8f0; --muted: #94a3b8; --accent: #38bdf8;
  }}
  * {{ box-sizing: border-box; margin: 0; }}
  body {{
    background: var(--bg); color: var(--text); padding: 40px 24px;
    font: 15px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }}
  .wrap {{ max-width: 960px; margin: 0 auto; }}
  h1 {{ font-size: 26px; }} h1 span {{ color: var(--accent); }}
  .meta {{ color: var(--muted); margin: 4px 0 28px; font-size: 13px; }}
  h2 {{ font-size: 17px; margin: 36px 0 14px; color: var(--accent); }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; }}
  .card {{
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 10px; padding: 18px;
  }}
  .card .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }}
  .card .value {{ font-size: 24px; font-weight: 700; margin-top: 6px; word-break: break-all; }}
  .card .sub {{ display: block; color: var(--muted); font-size: 12px; font-weight: 400; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; background: var(--panel); border-radius: 10px; overflow: hidden; }}
  th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--line); font-size: 14px; }}
  th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }}
  tr:last-child td {{ border-bottom: none; }}
  .pill {{ padding: 2px 10px; border-radius: 99px; font-size: 12px; font-weight: 600; color: #0f172a; }}
  .bar {{ background: var(--line); border-radius: 4px; height: 8px; min-width: 90px; }}
  .bar i {{ display: block; height: 100%; border-radius: 4px; }}
  .hub {{ background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 18px; margin-bottom: 12px; }}
  .hub b {{ color: var(--accent); }}
  .hub .imps {{ color: var(--muted); font-size: 13px; margin-top: 6px; }}
  ol li {{ margin-bottom: 8px; }}
  .empty {{ color: var(--muted); }}
  code {{ background: #0b1220; padding: 1px 6px; border-radius: 4px; font-size: 13px; }}
  footer {{ margin-top: 40px; color: var(--muted); font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>GapMap <span>Report</span></h1>
  <div class="meta">Repository: <code>{html.escape(str(analysis.root))}</code></div>

  <div class="cards">
    <div class="card"><div class="label">Files scanned</div><div class="value">{total}</div></div>
    <div class="card"><div class="label">Load-bearing files</div><div class="value">{len(bearing)}</div></div>
    <div class="card"><div class="label">Undocumented risks</div><div class="value">{len(gaps)}</div></div>
    <div class="card"><div class="label">ADR / doc coverage</div><div class="value">{coverage:.0%}<span class="sub">of load-bearing files mentioned in docs</span></div></div>
    <div class="card"><div class="label">Highest-risk file</div><div class="value">{top_card}</div></div>
  </div>

  <h2>Top undocumented risk files</h2>
  <table>
    <tr><th>#</th><th>File</th><th>Imported by</th><th>LOC</th><th>Risk score</th><th></th></tr>
    {rows}
  </table>

  <h2>Dependency map (biggest hubs)</h2>
  {dep_map}

  <h2>Recommended next actions</h2>
  <ol>{actions}</ol>

  <footer>Generated by GapMap - risk score = incoming dependencies x lines of code.</footer>
</div>
</body>
</html>
"""


def _risk_row(rank: int, risk: FileRisk, analysis: RepoAnalysis, max_score: int) -> str:
    level = risk_level(risk.score, max_score)
    color = _LEVEL_COLORS[level]
    width = int(100 * risk.score / max_score) if max_score else 0
    return (
        f"<tr><td>{rank}</td>"
        f"<td><code>{html.escape(risk.path)}</code></td>"
        f"<td>{risk.incoming}</td><td>{risk.loc}</td>"
        f"<td>{risk.score:,} "
        f'<span class="pill" style="background:{color}">{level}</span></td>'
        f'<td><div class="bar"><i style="width:{width}%;background:{color}"></i></div></td></tr>'
    )


def _hub_block(risk: FileRisk, analysis: RepoAnalysis) -> str:
    importers = analysis.importers_of(risk.path)
    shown = ", ".join(f"<code>{html.escape(i)}</code>" for i in importers[:8])
    more = f" +{len(importers) - 8} more" if len(importers) > 8 else ""
    return (
        f'<div class="hub"><b>{html.escape(risk.path)}</b> '
        f"&larr; imported by {risk.incoming} file(s)"
        f'<div class="imps">{shown}{more}</div></div>'
    )


def _actions(analysis: RepoAnalysis, gaps: List[FileRisk]) -> List[str]:
    actions = []
    for risk in gaps[:3]:
        actions.append(
            f"Generate an ADR for {risk.path} "
            f"(gapmap generate {Path(risk.path).name}) - "
            f"{risk.incoming} files depend on it and no docs mention it."
        )
    if not actions:
        actions.append(
            "No urgent gaps. Re-run the audit after major changes to catch drift."
        )
    else:
        actions.append(
            "Review generated ADRs with the original authors and commit them to docs/."
        )
        actions.append(
            "Re-run gapmap audit in CI to track documentation debt over time."
        )
    return actions
