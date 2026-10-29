"""Browser regression test for current and unusually wide DEFCON xGW values."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from day3.run_notebook import SCENE_DESIGN_CELL_INDEX, _patch_defcon_team_numeric_fit


def _assigned_literal(source: str, name: str) -> str:
    for statement in ast.parse(source).body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in statement.targets
        ):
            value = ast.literal_eval(statement.value)
            if not isinstance(value, str):
                raise RuntimeError(f"{name} must be a string")
            return value
    raise RuntimeError(f"Missing production scene source: {name}")


def check_defcon_forecasts(notebook_path: Path) -> None:
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    cells = notebook.get("cells")
    if not isinstance(cells, list) or len(cells) <= SCENE_DESIGN_CELL_INDEX:
        raise RuntimeError("Day 3 notebook has no DEFCON scene")

    cell = cells[SCENE_DESIGN_CELL_INDEX]
    raw_source = cell["source"]
    source = "".join(raw_source) if isinstance(raw_source, list) else str(raw_source)
    patched = _patch_defcon_team_numeric_fit(source)
    stylesheet = _assigned_literal(patched, "_D3_DEFCON_PRODUCTION_CSS")
    runtime_script = _assigned_literal(patched, "_D3_DEFCON_CARD_RUNTIME")

    start = runtime_script.find("  const fitDefconTeamForecasts=()=>{")
    end = runtime_script.find("  const assertDefconBoardFit=()=>{", start)
    if start == -1 or end <= start:
        raise RuntimeError("DEFCON numeric fitter was not installed in production runtime")

    fitter = runtime_script[start:end]
    sample_values = ["104.4", "999.9", "9999.9", "100.0", "88.8"] * 4
    rows = "".join(
        '<div class="d3DefTeamRow" data-team-id="' + str(index + 1) + '">'
        '<span class="d3DefTeamRank">01</span>'
        '<span class="d3DefTeamBadge"></span>'
        '<strong class="d3DefTeamName">Club Name</strong>'
        '<span class="d3DefTeamPrev"><strong>750</strong><small>75.00</small></span>'
        '<strong class="d3DefTeamForecast">' + value + '</strong>'
        '<span class="d3DefTeamTrend up">↑</span>'
        '</div>'
        for index, value in enumerate(sample_values)
    )
    page_html = (
        "<!doctype html><html><head><style>:root{--vx-dense:Arial,sans-serif}"
        ".d3DefTeamRow{width:850px;height:130px}</style>"
        + stylesheet
        + "</head><body class=\"vxPremium\">"
        + rows
        + "<script>(()=>{" + fitter
        + "window.testDefconNumericFit=fitDefconTeamForecasts;})();</script>"
        + "</body></html>"
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 3840, "height": 2160})
            page.set_content(page_html, wait_until="load")
            page.evaluate("async()=>{await document.fonts.ready;window.testDefconNumericFit()}")
            result = page.evaluate("""()=>{
                const elements=[...document.querySelectorAll('.d3DefTeamForecast')];
                return elements.map(element=>{
                  const box=element.getBoundingClientRect();
                  const range=document.createRange();
                  range.selectNodeContents(element);
                  const text=range.getBoundingClientRect();
                  return {
                    text:element.textContent.trim(),
                    fontSize:parseFloat(getComputedStyle(element).fontSize),
                    fits:text.left>=box.left+1 && text.right<=box.right-1
                      && element.scrollWidth<=element.clientWidth+1
                  };
                });
            }""")
            if len(result) != 20:
                raise AssertionError(f"Expected 20 live forecasts; found {len(result)}")
            overflow = [item for item in result if not item["fits"]]
            if overflow:
                raise AssertionError(f"DEFCON live forecast clips after fit: {overflow}")
            if any(item["fontSize"] < 32 for item in result):
                raise AssertionError("DEFCON fitter used unreadable type below 32px")
            if result[0]["fontSize"] >= 61:
                raise AssertionError("104.4 regression value was not resized to fit")
            print("✅ DEFCON 20-team live forecast browser test passed, including 104.4 and 9999.9")
        finally:
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("notebook", type=Path)
    args = parser.parse_args()
    if not args.notebook.is_file():
        raise FileNotFoundError(args.notebook)
    check_defcon_forecasts(args.notebook)


if __name__ == "__main__":
    main()
