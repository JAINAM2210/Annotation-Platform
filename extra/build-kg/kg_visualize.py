from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
DEFAULT_INPUT = DATA_DIR / "relation_candidates.csv"
DEFAULT_OUTPUT_DIR = DATA_DIR / "visualization"

DEFAULT_COLORS = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
    "#4e79a7",
    "#f28e2b",
    "#59a14f",
    "#e15759",
]


def load_relation_candidates(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def choose_default_paper(rows: Iterable[dict[str, str]]) -> str | None:
    counts = Counter(row["paper_title"] for row in rows)
    if not counts:
        return None
    return min(counts.items(), key=lambda item: (item[1], item[0]))[0]


def filter_rows(
    rows: list[dict[str, str]],
    *,
    paper_title: str | None,
    predicates: set[str] | None,
) -> list[dict[str, str]]:
    filtered = rows
    if paper_title:
        filtered = [row for row in filtered if row["paper_title"] == paper_title]
    if predicates:
        filtered = [row for row in filtered if row["predicate"] in predicates]
    return filtered


def deduplicate_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str, str]] = set()
    unique_rows: list[dict[str, str]] = []
    for row in rows:
        key = (
            row["paper_title"],
            row["subject_text"],
            row["predicate"],
            row["object_text"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    return unique_rows


def trim_graph(
    rows: list[dict[str, str]],
    *,
    max_nodes: int,
    max_edges: int,
) -> list[dict[str, str]]:
    if not rows:
        return []

    degree = Counter()
    for row in rows:
        degree[row["subject_text"]] += 1
        degree[row["object_text"]] += 1

    ranked_nodes = [node for node, _ in degree.most_common(max_nodes)]
    kept_nodes = set(ranked_nodes)
    trimmed = [
        row
        for row in rows
        if row["subject_text"] in kept_nodes and row["object_text"] in kept_nodes
    ]

    if len(trimmed) > max_edges:
        trimmed = trimmed[:max_edges]

    return trimmed


def node_color_map(node_types: list[str]) -> dict[str, str]:
    color_by_type: dict[str, str] = {}
    for index, node_type in enumerate(sorted(set(node_types))):
        color_by_type[node_type] = DEFAULT_COLORS[index % len(DEFAULT_COLORS)]
    return color_by_type


def build_nodes_and_edges(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    nodes: dict[str, dict[str, str]] = {}
    edges: list[dict[str, str]] = []

    grouped_evidence: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for row in rows:
        grouped_evidence[
            (row["subject_text"], row["predicate"], row["object_text"])
        ].append(row.get("evidence_text", ""))

    node_types = {
        row["subject_type"] for row in rows if row["subject_type"]
    } | {
        row["object_type"] for row in rows if row["object_type"]
    }
    colors = node_color_map(sorted(node_types))

    for row in rows:
        subject = row["subject_text"]
        obj = row["object_text"]
        subject_type = row.get("subject_type", "")
        object_type = row.get("object_type", "")

        if subject not in nodes:
            nodes[subject] = {
                "Id": subject,
                "Label": subject,
                "Type": subject_type,
                "Color": colors.get(subject_type, "#999999"),
            }
        if obj not in nodes:
            nodes[obj] = {
                "Id": obj,
                "Label": obj,
                "Type": object_type,
                "Color": colors.get(object_type, "#999999"),
            }

    for index, row in enumerate(rows, start=1):
        key = (row["subject_text"], row["predicate"], row["object_text"])
        evidence = grouped_evidence[key][0]
        edge_title = (
            f"Paper: {row.get('paper_title', '')}<br>"
            f"Predicate: {row['predicate']}<br>"
            f"Origin: {row.get('relation_origin', '')}<br>"
            f"Evidence: {evidence}"
        )
        edges.append(
            {
                "Id": f"edge_{index:05d}",
                "Source": row["subject_text"],
                "Target": row["object_text"],
                "Label": row["predicate"],
                "Paper": row.get("paper_title", ""),
                "DOI": row.get("doi", ""),
                "SubjectType": row.get("subject_type", ""),
                "ObjectType": row.get("object_type", ""),
                "RelationOrigin": row.get("relation_origin", ""),
                "InheritedFrom": row.get("inherited_from", ""),
                "EvidenceText": evidence,
                "Title": edge_title,
            }
        )

    return list(nodes.values()), edges


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_html(nodes: list[dict[str, str]], edges: list[dict[str, str]], metadata: dict[str, object]) -> str:
    vis_nodes = []
    for node in nodes:
        vis_nodes.append(
            {
                "id": node["Id"],
                "label": node["Label"],
                "title": f"{node['Label']}<br>Type: {node['Type']}",
                "color": node["Color"],
                "group": node["Type"],
            }
        )

    vis_edges = []
    for edge in edges:
        vis_edges.append(
            {
                "id": edge["Id"],
                "from": edge["Source"],
                "to": edge["Target"],
                "label": edge["Label"],
                "title": edge["Title"],
                "arrows": "to",
            }
        )

    data_blob = {
        "nodes": vis_nodes,
        "edges": vis_edges,
        "metadata": metadata,
    }

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>KG Preview</title>
  <script src="https://unpkg.com/vis-network@9.1.9/dist/vis-network.min.js"></script>
  <style>
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background: #f7f7f7;
      color: #222;
    }}
    .wrap {{
      display: grid;
      grid-template-columns: 320px 1fr;
      min-height: 100vh;
    }}
    .panel {{
      padding: 20px;
      border-right: 1px solid #ddd;
      background: #ffffff;
      overflow-y: auto;
    }}
    .panel h1 {{
      margin-top: 0;
      font-size: 22px;
    }}
    .panel code {{
      font-size: 12px;
      background: #f0f0f0;
      padding: 2px 5px;
      border-radius: 4px;
    }}
    .meta {{
      margin-top: 18px;
      font-size: 14px;
      line-height: 1.55;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin: 8px 0;
      font-size: 13px;
    }}
    .swatch {{
      width: 14px;
      height: 14px;
      border-radius: 3px;
      border: 1px solid rgba(0,0,0,0.15);
    }}
    #network {{
      width: 100%;
      height: 100vh;
      background: #fafafa;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="panel">
      <h1>KG Preview</h1>
      <div class="meta">
        <div><strong>Paper:</strong> {metadata.get("paper_title") or "All papers"}</div>
        <div><strong>Predicates:</strong> {", ".join(metadata.get("predicates", [])) or "All predicates"}</div>
        <div><strong>Nodes:</strong> {metadata.get("node_count")}</div>
        <div><strong>Edges:</strong> {metadata.get("edge_count")}</div>
        <div><strong>Input:</strong> <code>{metadata.get("input_csv")}</code></div>
      </div>
      <div class="meta">
        Drag nodes to explore. Hover a node to see its type. Hover an edge to see the source paper and evidence sentence.
      </div>
      <div class="meta">
        <strong>Legend</strong>
        {''.join(f'<div class="legend-item"><span class="swatch" style="background:{item["color"]}"></span>{item["type"]}</div>' for item in metadata.get("legend", []))}
      </div>
    </div>
    <div id="network"></div>
  </div>

  <script>
    const payload = {json.dumps(data_blob, ensure_ascii=False)};
    const nodes = new vis.DataSet(payload.nodes);
    const edges = new vis.DataSet(payload.edges);
    const container = document.getElementById('network');
    const data = {{ nodes, edges }};
    const options = {{
      autoResize: true,
      interaction: {{
        hover: true,
        navigationButtons: true,
        tooltipDelay: 100
      }},
      physics: {{
        stabilization: false,
        barnesHut: {{
          gravitationalConstant: -4000,
          springLength: 140,
          springConstant: 0.02
        }}
      }},
      nodes: {{
        shape: 'dot',
        size: 18,
        font: {{
          size: 13,
          face: 'Arial'
        }},
        borderWidth: 1
      }},
      edges: {{
        smooth: true,
        width: 1.2,
        color: {{ color: '#7a7a7a', opacity: 0.7 }},
        font: {{
          size: 10,
          align: 'top'
        }}
      }}
    }};
    new vis.Network(container, data, options);
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Gephi CSV files and a browser preview from KG relation candidates."
    )
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Relation candidate CSV to visualize. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to write visualization artifacts. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--paper-title",
        help="Restrict the preview to a single paper title. Defaults to the smallest paper subgraph.",
    )
    parser.add_argument(
        "--predicate",
        action="append",
        dest="predicates",
        help="Restrict the preview to one or more predicates. Repeat the flag to add more.",
    )
    parser.add_argument(
        "--max-nodes",
        type=int,
        default=60,
        help="Maximum number of nodes to retain after ranking by degree. Default: 60",
    )
    parser.add_argument(
        "--max-edges",
        type=int,
        default=120,
        help="Maximum number of edges to include in the preview. Default: 120",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_relation_candidates(args.input_csv)

    paper_title = args.paper_title or choose_default_paper(rows)
    predicates = set(args.predicates) if args.predicates else None

    filtered = filter_rows(rows, paper_title=paper_title, predicates=predicates)
    filtered = deduplicate_rows(filtered)
    filtered = trim_graph(filtered, max_nodes=args.max_nodes, max_edges=args.max_edges)
    nodes, edges = build_nodes_and_edges(filtered)

    legend = [
        {"type": node_type, "color": color}
        for node_type, color in sorted(node_color_map([node["Type"] for node in nodes]).items())
    ]
    metadata = {
        "input_csv": str(args.input_csv),
        "paper_title": paper_title,
        "predicates": sorted(predicates) if predicates else [],
        "node_count": len(nodes),
        "edge_count": len(edges),
        "legend": legend,
        "max_nodes": args.max_nodes,
        "max_edges": args.max_edges,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        args.output_dir / "gephi_nodes.csv",
        nodes,
        ["Id", "Label", "Type", "Color"],
    )
    write_csv(
        args.output_dir / "gephi_edges.csv",
        edges,
        [
            "Id",
            "Source",
            "Target",
            "Label",
            "Paper",
            "DOI",
            "SubjectType",
            "ObjectType",
            "RelationOrigin",
            "InheritedFrom",
            "EvidenceText",
            "Title",
        ],
    )
    (args.output_dir / "preview_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (args.output_dir / "kg_preview.html").write_text(
        build_html(nodes, edges, metadata),
        encoding="utf-8",
    )

    print(json.dumps(metadata, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
