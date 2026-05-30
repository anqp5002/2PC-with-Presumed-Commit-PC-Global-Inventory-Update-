from __future__ import annotations

import argparse
import csv
from html import escape
from pathlib import Path

try:
    from scripts.collect_metrics import MESSAGE_COUNT_CSV
except ModuleNotFoundError:
    from collect_metrics import MESSAGE_COUNT_CSV


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "message_counts_chart.svg"


def read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_svg(rows: list[dict[str, str]]) -> str:
    width = 920
    height = 520
    margin_left = 80
    margin_right = 40
    margin_top = 50
    margin_bottom = 130
    chart_width = width - margin_left - margin_right
    chart_height = height - margin_top - margin_bottom
    max_total = max(int(row["actual_total"]) for row in rows)
    y_max = max(20, ((max_total + 3) // 4) * 4)
    bar_gap = 24
    bar_width = (chart_width - bar_gap * (len(rows) - 1)) / len(rows)
    colors = {
        "PA_COMPARISON": "#4f46e5",
        "PC_NO_ACD": "#059669",
        "PC_WITH_ACD": "#dc2626",
    }

    def x_at(index: int) -> float:
        return margin_left + index * (bar_width + bar_gap)

    def y_at(value: int) -> float:
        return margin_top + chart_height - (value / y_max) * chart_height

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:Arial,Helvetica,sans-serif}.title{font-size:22px;font-weight:700}.axis{font-size:12px;fill:#374151}.label{font-size:12px;fill:#111827}.value{font-size:13px;font-weight:700;fill:#111827}.grid{stroke:#e5e7eb;stroke-width:1}.axis-line{stroke:#111827;stroke-width:1.4}</style>',
        f'<text x="{width / 2}" y="30" text-anchor="middle" class="title">PA vs PC Message Count</text>',
    ]

    for tick in range(0, y_max + 1, 4):
        y = y_at(tick)
        parts.append(
            f'<line x1="{margin_left}" y1="{y:.1f}" x2="{width - margin_right}" y2="{y:.1f}" class="grid"/>'
        )
        parts.append(
            f'<text x="{margin_left - 10}" y="{y + 4:.1f}" text-anchor="end" class="axis">{tick}</text>'
        )

    parts.extend(
        [
            f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + chart_height}" class="axis-line"/>',
            f'<line x1="{margin_left}" y1="{margin_top + chart_height}" x2="{width - margin_right}" y2="{margin_top + chart_height}" class="axis-line"/>',
            f'<text x="24" y="{margin_top + chart_height / 2}" text-anchor="middle" transform="rotate(-90 24 {margin_top + chart_height / 2})" class="axis">Network message count</text>',
        ]
    )

    for index, row in enumerate(rows):
        total = int(row["actual_total"])
        x = x_at(index)
        y = y_at(total)
        bar_height = margin_top + chart_height - y
        color = colors.get(row["mode"], "#6b7280")
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" rx="3" fill="{color}"/>'
        )
        parts.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{y - 8:.1f}" text-anchor="middle" class="value">{total}</text>'
        )
        label = escape(row["case_name"])
        parts.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{margin_top + chart_height + 28}" text-anchor="middle" class="label">{label}</text>'
        )
        parts.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{margin_top + chart_height + 46}" text-anchor="middle" class="axis">{escape(row["mode"])}</text>'
        )

    legend_x = margin_left
    legend_y = height - 36
    for idx, (mode, color) in enumerate(colors.items()):
        x = legend_x + idx * 210
        parts.append(f'<rect x="{x}" y="{legend_y}" width="14" height="14" fill="{color}"/>')
        parts.append(f'<text x="{x + 22}" y="{legend_y + 12}" class="axis">{mode}</text>')

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def plot_message_counts(
    csv_path: Path = MESSAGE_COUNT_CSV,
    output_path: Path = DEFAULT_OUTPUT,
) -> Path:
    rows = read_rows(csv_path)
    svg = build_svg(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot PA vs PC message counts as SVG.")
    parser.add_argument("--input", type=Path, default=MESSAGE_COUNT_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    output = plot_message_counts(args.input, args.output)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
