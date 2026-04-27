"""Shared look for Plotly HTML exports: theme, spacing, and readable formatted files."""
from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from uuid import uuid4

import plotly.graph_objects as go
import plotly.io as pio
from plotly.basedatatypes import BaseFigure

_PLOTLY_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "responsive": True,
    "toImageButtonOptions": {"format": "png", "scale": 2},
}


@functools.lru_cache(maxsize=1)
def _plotly_cdn_src() -> str:
    """Use the same plotly.js version as pio.to_html would for this install."""
    html = pio.to_html(go.Figure(), full_html=True, include_plotlyjs="cdn")
    m = re.search(r"https://cdn\.plot\.ly/plotly-[^\"']+\.min\.js", html)
    if m:
        return m.group(0)
    return "https://cdn.plot.ly/plotly-3.5.0.min.js"


def _json_safe_inside_script_type_application_json(s: str) -> str:
    """
    So that user text cannot accidentally form `</` + `script` and close
    the tag before the JSON block ends, break each `</` in the file as
    `<` + JSON escape to `/` (so the on-disk file does not contain a raw
    less-than + solidus in that form).
    """
    return s.replace("</", r"<\u002f")


def apply_report_style(fig: BaseFigure) -> None:
    fig.update_layout(
        template="plotly_white",
        font=dict(
            family="Segoe UI, system-ui, -apple-system, Roboto, Helvetica Neue, sans-serif",
            size=13,
            color="#1e293b",
        ),
        title_font=dict(size=18, color="#0f172a"),
        title_x=0.5,
        title_xanchor="center",
        title_pad=dict(t=12, b=12),
        paper_bgcolor="#f8fafc",
        plot_bgcolor="#ffffff",
        legend=dict(
            bgcolor="rgba(248,250,252,0.95)",
            bordercolor="#e2e8f0",
            borderwidth=1,
            font=dict(size=12),
        ),
        colorway=["#0284c7", "#dc2626", "#7c3aed", "#0d9488", "#ea580c", "#4f46e5"],
    )


def write_report_html(fig: BaseFigure, path: Path | str) -> None:
    """
    Apply theme, write full HTML with CDN plotly. The figure is stored as
    pretty-printed JSON in a <script type="application/json"> block, so
    the file is line-wrapped for editors (unlike pio.to_html, which
    inlines a single minified Plotly.newPlot call).
    """
    path = Path(path)
    apply_report_style(fig)
    cdn = _plotly_cdn_src()
    fig_json = pio.to_json(fig, pretty=True, remove_uids=True)
    fig_block = _json_safe_inside_script_type_application_json(fig_json)
    config_json = json.dumps(_PLOTLY_CONFIG, indent=2, ensure_ascii=False)
    div_id = f"plotly-div-{uuid4().hex[:10]}"
    data_id = f"fig-json-{uuid4().hex[:10]}"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Report chart</title>
  <script src="{cdn}" charset="utf-8" crossorigin="anonymous"></script>
  <style>
    body {{ font-family: Segoe UI, system-ui, sans-serif; margin: 0; background: #f8fafc; }}
    #plot-wrap {{ padding: 12px; }}
  </style>
</head>
<body>
  <div id="plot-wrap">
    <div id="{div_id}"></div>
  </div>
  <script type="application/json" id="{data_id}">{fig_block}</script>
  <script>
  (function() {{
    var el = document.getElementById("{div_id}");
    var raw = document.getElementById("{data_id}").textContent;
    var fig = JSON.parse(raw);
    var cfg = {config_json};
    if (fig.frames && fig.frames.length) {{
      Plotly.newPlot(el, fig.data, fig.layout, cfg).then(function() {{
        return Plotly.addFrames(el, fig.frames);
      }});
    }} else {{
      Plotly.newPlot(el, fig.data, fig.layout, cfg);
    }}
  }})();
  </script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")
