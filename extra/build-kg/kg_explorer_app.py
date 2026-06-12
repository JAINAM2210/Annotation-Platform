from __future__ import annotations

import html
import json
import re
from urllib.parse import urlencode
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from kg_visualize import (
    DATA_DIR,
    DEFAULT_INPUT,
    build_html,
    build_nodes_and_edges,
    deduplicate_rows,
    trim_graph,
)


DEFAULT_HEIGHT = 900
EDITED_OUTPUT_DIR = DATA_DIR / "relations"
DATASET_OPTIONS = {
    "Raw candidates": DEFAULT_INPUT,
}


@st.cache_data(show_spinner=False)
def load_graph_dataframe(csv_path: str, dataset_label: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["accepted"] = True

    for column in [
        "paper_title",
        "predicate",
        "subject_type",
        "object_type",
        "relation_origin",
        "inherited_from",
        "subject_text",
        "object_text",
        "evidence_text",
        "doi",
        "support_sentence_ids",
        "paper_id",
        "relation_id",
    ]:
        if column not in df.columns:
            df[column] = ""

    if "confidence" not in df.columns:
        df["confidence"] = None

    return df


@st.cache_data(show_spinner=False)
def load_summary(summary_path: str) -> dict[str, object]:
    path = Path(summary_path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def load_paper_index(csv_path: str) -> pd.DataFrame:
    return pd.read_csv(csv_path)


@st.cache_data(show_spinner=False)
def load_sentence_index(csv_path: str) -> pd.DataFrame:
    return pd.read_csv(csv_path)


@st.cache_data(show_spinner=False)
def load_allowed_predicates(csv_path: str) -> list[str]:
    df = pd.read_csv(csv_path)
    if "predicate" not in df.columns:
        return []
    return sorted(df["predicate"].dropna().astype(str).unique().tolist())


@st.cache_data(show_spinner=False)
def load_edited_graph_catalog(edited_dir: str) -> dict[str, object]:
    base = Path(edited_dir)
    if not base.exists():
        return {"nested": {}, "legacy": {}}

    nested: dict[str, dict[str, dict[str, str]]] = {}
    legacy: dict[str, str] = {}
    for csv_path in sorted(base.rglob("*.csv")):
        relative_parts = csv_path.relative_to(base).parts

        if len(relative_parts) == 2:
            paper_id, filename = relative_parts
            nested.setdefault("relations", {}).setdefault(paper_id, {})[filename] = str(csv_path)
        elif len(relative_parts) == 3:
            dataset_slug, paper_id, filename = relative_parts
            nested.setdefault(dataset_slug, {}).setdefault(paper_id, {})[filename] = str(csv_path)
        else:
            label = csv_path.stem
            if label.endswith("_edited_graph"):
                label = label[: -len("_edited_graph")]
            legacy[label] = str(csv_path)
    return {"nested": nested, "legacy": legacy}


def filter_dataframe(
    df: pd.DataFrame,
    *,
    paper_title: str,
    predicates: list[str],
    subject_types: list[str],
    object_types: list[str],
    relation_origins: list[str],
    search_text: str,
    accepted_only: bool,
) -> pd.DataFrame:
    filtered = df

    if accepted_only and "accepted" in filtered.columns:
        filtered = filtered[filtered["accepted"] == True]

    if paper_title != "All papers":
        filtered = filtered[filtered["paper_title"] == paper_title]
    if predicates:
        filtered = filtered[filtered["predicate"].isin(predicates)]
    if subject_types:
        filtered = filtered[filtered["subject_type"].isin(subject_types)]
    if object_types:
        filtered = filtered[filtered["object_type"].isin(object_types)]
    if relation_origins:
        filtered = filtered[filtered["relation_origin"].isin(relation_origins)]
    if search_text.strip():
        needle = search_text.strip().casefold()
        mask = (
            filtered["subject_text"].fillna("").str.casefold().str.contains(needle)
            | filtered["object_text"].fillna("").str.casefold().str.contains(needle)
            | filtered["evidence_text"].fillna("").str.casefold().str.contains(needle)
        )
        filtered = filtered[mask]

    return filtered


def dataframe_to_visualization(
    df: pd.DataFrame,
    *,
    max_nodes: int,
    max_edges: int,
    input_csv: str,
    paper_title: str,
    predicates: list[str],
) -> tuple[str, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    rows = df.to_dict(orient="records")
    rows = deduplicate_rows(rows)
    rows = trim_graph(rows, max_nodes=max_nodes, max_edges=max_edges)
    nodes, edges = build_nodes_and_edges(rows)

    legend_rows = []
    seen = set()
    for node in sorted(nodes, key=lambda item: (item["Type"], item["Label"])):
        key = (node["Type"], node["Color"])
        if key in seen:
            continue
        seen.add(key)
        legend_rows.append({"type": node["Type"], "color": node["Color"]})

    metadata = {
        "input_csv": input_csv,
        "paper_title": None if paper_title == "All papers" else paper_title,
        "predicates": predicates,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "legend": legend_rows,
        "max_nodes": max_nodes,
        "max_edges": max_edges,
    }

    html = build_html(nodes, edges, metadata)
    nodes_df = pd.DataFrame(nodes)
    edges_df = pd.DataFrame(edges)
    return html, nodes_df, edges_df, metadata


def relation_identifier(row: pd.Series) -> str:
    for key in ("candidate_id", "relation_id"):
        value = row.get(key)
        if pd.notna(value) and str(value).strip():
            return str(value)
    subject = str(row.get("subject_text", "")).strip()
    predicate = str(row.get("predicate", "")).strip()
    obj = str(row.get("object_text", "")).strip()
    evidence = str(row.get("evidence_text", "")).strip()[:60]
    return f"{subject}::{predicate}::{obj}::{evidence}"


def sentence_ids_for_row(row: pd.Series, sentence_df: pd.DataFrame) -> list[str]:
    if pd.notna(row.get("sentence_id")) and str(row.get("sentence_id")).strip():
        return [str(row.get("sentence_id"))]

    support_ids = str(row.get("support_sentence_ids", "") or "").strip()
    if support_ids:
        return [item for item in support_ids.split(";") if item]

    evidence_text = str(row.get("evidence_text", "") or "").strip()
    if evidence_text:
        matches = sentence_df.loc[sentence_df["text"] == evidence_text, "sentence_id"].tolist()
        return [str(item) for item in matches]

    return []


def ensure_editable_relation_columns(df: pd.DataFrame) -> pd.DataFrame:
    editable = df.copy()
    defaults = {
        "relation_id": "",
        "paper_id": "",
        "paper_title": "",
        "doi": "",
        "subject_text": "",
        "subject_type": "",
        "predicate": "",
        "object_text": "",
        "object_type": "",
        "confidence": "",
        "accepted": True,
        "evidence_text": "",
        "relation_origin": "",
        "inherited_from": "",
        "support_sentence_ids": "",
    }
    for column, default in defaults.items():
        if column not in editable.columns:
            editable[column] = default

    if editable["relation_id"].astype(str).str.strip().eq("").all():
        editable["relation_id"] = [f"editable_{idx:06d}" for idx in range(1, len(editable) + 1)]
    editable["accepted"] = editable["accepted"].fillna(True)
    return editable[
        [
            "relation_id",
            "paper_id",
            "paper_title",
            "doi",
            "subject_text",
            "subject_type",
            "predicate",
            "object_text",
            "object_type",
            "confidence",
            "accepted",
            "evidence_text",
            "relation_origin",
            "inherited_from",
            "support_sentence_ids",
        ]
    ].copy()


def init_editable_relations(
    dataset_label: str,
    paper_id: str,
    paper_title: str,
    doi: str,
    source_df: pd.DataFrame,
    sentence_df: pd.DataFrame,
) -> pd.DataFrame:
    editable = ensure_editable_relation_columns(source_df)
    editable["paper_id"] = paper_id
    editable["paper_title"] = paper_title
    editable["doi"] = doi
    editable["support_sentence_ids"] = [
        ";".join(sentence_ids_for_row(row, sentence_df))
        for _, row in source_df.iterrows()
    ]
    editable["relation_origin"] = editable["relation_origin"].replace(
        "", dataset_label.casefold().replace(" ", "_")
    )
    editable["accepted"] = editable["accepted"].fillna(True)
    return editable.reset_index(drop=True)


def _first_query_param(name: str) -> str:
    value = st.query_params.get(name, "")
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value)


def _list_query_param(name: str) -> list[str]:
    value = st.query_params.get(name, [])
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value:
        return [str(value)]
    return []


def clear_delete_query_params() -> None:
    for key in ["delete_rel", "delete_session", "delete_sentence"]:
        try:
            del st.query_params[key]
        except Exception:
            pass


def build_ui_query_params(ui_state: dict[str, object]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for key, value in ui_state.items():
        if isinstance(value, list):
            for item in value:
                if str(item):
                    pairs.append((key, str(item)))
        elif isinstance(value, bool):
            pairs.append((key, "1" if value else "0"))
        elif value is not None and str(value) != "":
            pairs.append((key, str(value)))
    return pairs


def build_relation_strip_html(
    relations: list[dict[str, str]],
    session_key: str,
    sentence_id: str,
    ui_state: dict[str, object],
) -> str:
    pills: list[str] = []
    for rel in relations:
        rel_id = str(rel.get("relation_id", ""))
        pill_label = (
            f"{html.escape(str(rel.get('subject_text', '')).strip())} → "
            f"<strong>{html.escape(str(rel.get('predicate', '')).strip())}</strong> → "
            f"{html.escape(str(rel.get('object_text', '')).strip())}"
        )
        query = urlencode(
            build_ui_query_params(ui_state)
            + [
                ("delete_rel", rel_id),
                ("delete_session", session_key),
                ("delete_sentence", sentence_id),
            ]
        )
        pills.append(
            '<span class="relation-pill-html">'
            f'<span class="relation-pill-label">{pill_label}</span>'
            f'<a class="relation-pill-delete" href="?{query}#{sentence_id}" target="_self" title="Delete relation">×</a>'
            '</span>'
        )
    return f'<div class="relation-pill-strip">{"".join(pills)}</div>'


def highlight_sentence_text(sentence_text: str, mentions: list[tuple[str, str]]) -> str:
    if not mentions:
        return html.escape(sentence_text)

    ranges: list[tuple[int, int, str, str]] = []
    seen = set()
    for mention_text, role in sorted(mentions, key=lambda item: len(item[0]), reverse=True):
        normalized = mention_text.strip()
        if not normalized:
            continue
        pattern = re.compile(re.escape(normalized), re.IGNORECASE)
        for match in pattern.finditer(sentence_text):
            start, end = match.span()
            key = (start, end, role)
            if key in seen:
                continue
            if any(not (end <= existing_start or start >= existing_end) for existing_start, existing_end, _, _ in ranges):
                continue
            seen.add(key)
            label = "Subject" if role == "subject" else "Object"
            css = (
                "background:#d7ecff;border-bottom:2px solid #2b7de9;padding:0 2px;border-radius:3px;"
                if role == "subject"
                else "background:#ffe4c2;border-bottom:2px solid #d97706;padding:0 2px;border-radius:3px;"
            )
            ranges.append((start, end, css, label))

    if not ranges:
        return html.escape(sentence_text)

    ranges.sort(key=lambda item: item[0])
    cursor = 0
    parts: list[str] = []
    for start, end, css, label in ranges:
        if start > cursor:
            parts.append(html.escape(sentence_text[cursor:start]))
        span_text = html.escape(sentence_text[start:end])
        parts.append(f'<span title="{label}" style="{css}">{span_text}</span>')
        cursor = end
    if cursor < len(sentence_text):
        parts.append(html.escape(sentence_text[cursor:]))
    return "".join(parts)


@st.fragment
def render_sentence_relation_workspace(
    dataset_label: str,
    paper_row: pd.Series,
    sentence_df: pd.DataFrame,
    editable_df: pd.DataFrame,
    session_key: str,
    allowed_predicates: list[str],
    ui_state: dict[str, object],
) -> None:
    relation_map: dict[str, list[dict[str, str]]] = {
        sentence_id: [] for sentence_id in sentence_df["sentence_id"].tolist()
    }

    for _, row in editable_df.iterrows():
        support_ids = [item for item in str(row.get("support_sentence_ids", "")).split(";") if item]
        if not support_ids and str(row.get("evidence_text", "")).strip():
            matches = sentence_df.loc[sentence_df["text"] == row["evidence_text"], "sentence_id"].tolist()
            support_ids = [str(item) for item in matches]
        for sentence_id in support_ids:
            if sentence_id in relation_map:
                relation_map[sentence_id].append(row.to_dict())

    st.markdown("### Paper Text And Extracted Relations")
    st.caption(f"Selected dataset: {dataset_label}")
    st.markdown(f"**Paper:** {paper_row['title']}")
    st.markdown(f"**DOI:** {paper_row['doi']}")

    for _, sentence in sentence_df.iterrows():
        sentence_id = sentence["sentence_id"]
        relations = relation_map.get(sentence_id, [])
        mentions: list[tuple[str, str]] = []
        entity_map: dict[str, str] = {}
        for rel in relations:
            subject_text = str(rel.get("subject_text", ""))
            object_text = str(rel.get("object_text", ""))
            subject_type = str(rel.get("subject_type", ""))
            object_type = str(rel.get("object_type", ""))
            mentions.append((subject_text, "subject"))
            mentions.append((object_text, "object"))
            if subject_text:
                entity_map[subject_text] = subject_type
            if object_text:
                entity_map[object_text] = object_type
        highlighted = highlight_sentence_text(sentence["text"], mentions)

        st.markdown(f'<div id="{sentence_id}" class="sentence-anchor"></div>', unsafe_allow_html=True)
        with st.expander(f"Sentence {int(sentence['sentence_index'])}", expanded=bool(relations)):
            st.markdown(
                f'<div style="line-height:1.8;font-size:15px;">{highlighted}</div>',
                unsafe_allow_html=True,
            )
            if relations:
                st.markdown("**Relations**")
                relation_rows: list[list[dict[str, str]]] = []
                current_row: list[dict[str, str]] = []
                current_width = 0
                for rel in relations:
                    approx_width = min(
                        max(
                            len(str(rel.get("subject_text", "")))
                            + len(str(rel.get("predicate", "")))
                            + len(str(rel.get("object_text", "")))
                            + 8,
                            24,
                        ),
                        64,
                    )
                    if current_row and current_width + approx_width > 250:
                        relation_rows.append(current_row)
                        current_row = []
                        current_width = 0
                    current_row.append(rel)
                    current_width += approx_width
                if current_row:
                    relation_rows.append(current_row)

                for relation_row in relation_rows:
                    column_widths = [
                        min(
                            max(
                                len(str(rel.get("subject_text", "")))
                                + len(str(rel.get("predicate", "")))
                                + len(str(rel.get("object_text", "")))
                                + 8,
                                16,
                            ),
                            52,
                        )
                        for rel in relation_row
                    ]
                    row_cols = st.columns(column_widths, gap="small")
                    for col, rel in zip(row_cols, relation_row):
                        rel_id = str(rel.get("relation_id", ""))
                        pill_label = (
                            f"{html.escape(str(rel.get('subject_text', '')).strip())} → "
                            f"<strong>{html.escape(str(rel.get('predicate', '')).strip())}</strong> → "
                            f"{html.escape(str(rel.get('object_text', '')).strip())}"
                        )
                        with col:
                            inner_cols = st.columns([100, 1], gap="small")
                            with inner_cols[0]:
                                st.markdown(
                                    f'<div class="relation-pill-static">{pill_label}</div>',
                                    unsafe_allow_html=True,
                                )
                            with inner_cols[1]:
                                st.markdown('<div class="relation-pill-close">', unsafe_allow_html=True)
                                if st.button(
                                    "×",
                                    key=f"inline_delete::{session_key}::{sentence_id}::{rel_id}",
                                    help="Delete this relation",
                                    type="secondary",
                                    use_container_width=False,
                                ):
                                    updated = editable_df.loc[editable_df["relation_id"] != rel_id].reset_index(drop=True)
                                    st.session_state[session_key] = updated
                                    st.rerun(scope="fragment")
                                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.caption("No extracted relations tied to this sentence in the selected graph version.")

            entity_options = [f"{text} [{etype}]" for text, etype in sorted(entity_map.items())]
            entity_lookup = {f"{text} [{etype}]": (text, etype) for text, etype in sorted(entity_map.items())}
            st.markdown("**Add relation to this sentence**")
            if len(entity_options) >= 2:
                with st.form(key=f"inline_add_relation_form::{session_key}::{sentence_id}"):
                    col1, col2, col3 = st.columns([1.2, 1.2, 1.6])
                    with col1:
                        subject_choice = st.selectbox(
                            "Subject entity",
                            entity_options,
                            key=f"subject_choice::{session_key}::{sentence_id}",
                        )
                    with col2:
                        object_choice = st.selectbox(
                            "Object entity",
                            entity_options,
                            key=f"object_choice::{session_key}::{sentence_id}",
                        )
                    with col3:
                        predicate = st.selectbox(
                            "Predicate",
                            allowed_predicates,
                            key=f"predicate::{session_key}::{sentence_id}",
                        )
                    inherited_from = st.text_input(
                        "Inherited from",
                        value="",
                        key=f"inherited_from::{session_key}::{sentence_id}",
                    )
                    submitted = st.form_submit_button("Add relation to this sentence")

                if submitted:
                    subject_text, subject_type = entity_lookup[subject_choice]
                    object_text, object_type = entity_lookup[object_choice]
                    new_relation = {
                        "relation_id": f"manual_{len(editable_df) + 1:06d}",
                        "paper_id": str(paper_row["paper_id"]),
                        "paper_title": str(paper_row["title"]),
                        "doi": str(paper_row["doi"]),
                        "subject_text": subject_text.strip(),
                        "subject_type": subject_type.strip(),
                        "predicate": predicate.strip(),
                        "object_text": object_text.strip(),
                        "object_type": object_type.strip(),
                        "confidence": "1.0",
                        "accepted": True,
                        "evidence_text": str(sentence["text"]),
                        "relation_origin": "manual_edit",
                        "inherited_from": inherited_from.strip(),
                        "support_sentence_ids": sentence_id,
                    }
                    updated = pd.concat([editable_df, pd.DataFrame([new_relation])], ignore_index=True)
                    st.session_state[session_key] = updated
                    st.rerun(scope="fragment")
            else:
                st.caption("Need at least two highlighted entities in this sentence before a relation can be added here.")


def relation_option_label(row: pd.Series) -> str:
    return (
        f"{row.get('relation_id', relation_identifier(row))} | "
        f"{row.get('subject_text', '')} -> {row.get('predicate', '')} -> {row.get('object_text', '')}"
    )


def save_editable_relations(dataset_label: str, paper_id: str, editable_df: pd.DataFrame) -> Path:
    EDITED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = EDITED_OUTPUT_DIR / paper_id / "latest.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    editable_df.to_csv(output_path, index=False)
    return output_path


def render_dataset_panel(
    title: str,
    df: pd.DataFrame,
    *,
    max_nodes: int,
    max_edges: int,
    input_csv: str,
    paper_title: str,
    predicates: list[str],
    height: int,
) -> None:
    html_blob, nodes_df, edges_df, metadata = dataframe_to_visualization(
        df,
        max_nodes=max_nodes,
        max_edges=max_edges,
        input_csv=input_csv,
        paper_title=paper_title,
        predicates=predicates,
    )

    st.markdown(f"### {title}")
    top = st.columns(4)
    top[0].metric("Rows after filters", f"{len(df):,}")
    top[1].metric("Preview nodes", f"{metadata['node_count']:,}")
    top[2].metric("Preview edges", f"{metadata['edge_count']:,}")
    confidence_values = df["confidence"].dropna() if "confidence" in df.columns else pd.Series(dtype=float)
    mean_confidence = f"{confidence_values.astype(float).mean():.2f}" if not confidence_values.empty else "N/A"
    top[3].metric("Mean confidence", mean_confidence)

    if edges_df.empty:
        st.warning("No edges match the current filters.")
    else:
        components.html(html_blob, height=height, scrolling=True)

    tabs = st.tabs(["Edges", "Nodes"])
    with tabs[0]:
        st.dataframe(edges_df, width="stretch", height=260)
        st.download_button(
            f"Download {title} edges CSV",
            edges_df.to_csv(index=False).encode("utf-8"),
            file_name=f"{title.lower().replace(' ', '_')}_edges.csv",
            mime="text/csv",
            key=f"download_edges_{title}",
        )
    with tabs[1]:
        st.dataframe(nodes_df, width="stretch", height=260)
        st.download_button(
            f"Download {title} nodes CSV",
            nodes_df.to_csv(index=False).encode("utf-8"),
            file_name=f"{title.lower().replace(' ', '_')}_nodes.csv",
            mime="text/csv",
            key=f"download_nodes_{title}",
        )


def main() -> None:
    st.set_page_config(page_title="KG Explorer", layout="wide")

    default_summary_path = DATA_DIR / "schema_summary.json"
    summary = load_summary(str(default_summary_path))
    raw_df = load_graph_dataframe(str(DEFAULT_INPUT), "Raw candidates")
    paper_index = load_paper_index(str(DATA_DIR / "paper_index.csv"))
    sentence_index = load_sentence_index(str(DATA_DIR / "sentence_index.csv"))
    allowed_predicates = load_allowed_predicates(str(DATA_DIR / "relations.csv"))

    st.title("Knowledge Graph Explorer")
    st.caption(
        "Interactive explorer for the schema-constrained KG candidates generated from `data/relation_candidates.csv`."
    )
    st.markdown(
        """
        <style>
        div.relation-pill-static {
            display: inline-block;
            margin: 4px 0 0 0;
            padding: 4px 22px 4px 12px;
            border-radius: 999px;
            background: #eef2ff;
            border: 1px solid #c7d2fe;
            color: #31415f;
            font-size: 12px;
            line-height: 1.25;
            white-space: nowrap;
        }
        div.relation-pill-close {
            margin: 4px 0 0 -2.15rem;
            position: relative;
            z-index: 5;
        }
        div.relation-pill-close div[data-testid="stButton"] {
            width: 0.7rem;
        }
        div.relation-pill-close div[data-testid="stButton"] > button {
            min-width: 0.7rem;
            width: 0.7rem;
            height: 0.7rem;
            border-radius: 999px;
            border: none;
            background: transparent;
            color: #5a6783;
            padding: 0;
            line-height: 0.7;
            box-shadow: none;
            font-size: 0.8rem;
        }
        div.relation-pill-close div[data-testid="stButton"] > button:hover {
            border: none;
            background: transparent;
            color: #22304a;
        }
        div.sentence-anchor {
            position: relative;
            top: -10px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    edited_graph_catalog = load_edited_graph_catalog(str(EDITED_OUTPUT_DIR))
    has_edited_graphs = bool(edited_graph_catalog["nested"] or edited_graph_catalog["legacy"])
    dataset_options = list(DATASET_OPTIONS.keys()) + (["Edited graph"] if has_edited_graphs else [])
    dataset_default = _first_query_param("dataset") or dataset_options[0]
    if dataset_default not in dataset_options:
        dataset_default = dataset_options[0]
    edited_file_default = _first_query_param("edited_file")
    accepted_default = (_first_query_param("accepted") or "1") != "0"
    paper_default = _first_query_param("paper") or "All papers"
    predicate_defaults = _list_query_param("predicates")
    subject_type_defaults = _list_query_param("subject_types")
    object_type_defaults = _list_query_param("object_types")
    relation_origin_defaults = _list_query_param("relation_origins")
    search_default = _first_query_param("search_text")
    max_nodes_default = int(_first_query_param("max_nodes") or 60)
    max_edges_default = int(_first_query_param("max_edges") or 120)

    with st.sidebar:
        st.header("Filters")

        dataset_label = st.selectbox(
            "Graph version",
            dataset_options,
            index=dataset_options.index(dataset_default),
        )

        edited_file_label = None
        if dataset_label == "Edited graph":
            nested_catalog = edited_graph_catalog["nested"]
            legacy_catalog = edited_graph_catalog["legacy"]
            if not (nested_catalog or legacy_catalog):
                st.warning("No edited graph files found.")
                st.stop()

            source_options = []
            if nested_catalog:
                source_options.append("Nested edited folders")
            if legacy_catalog:
                source_options.append("Legacy edited files")
            edited_source = st.selectbox("Edited source", source_options)

            if edited_source == "Nested edited folders":
                dataset_folder_options = sorted(nested_catalog.keys())
                dataset_folder = st.selectbox("Dataset folder", dataset_folder_options)

                paper_folder_options = sorted(nested_catalog[dataset_folder].keys())
                paper_folder = st.selectbox("Paper folder", paper_folder_options)

                file_options = sorted(
                    nested_catalog[dataset_folder][paper_folder].keys(),
                    key=lambda name: (name != "latest.csv", name),
                )
                default_file = edited_file_default if edited_file_default in file_options else file_options[0]
                selected_file = st.selectbox("Edited file", file_options, index=file_options.index(default_file))
                selected_input_csv = nested_catalog[dataset_folder][paper_folder][selected_file]
                edited_file_label = f"{dataset_folder}/{paper_folder}/{selected_file}"
            else:
                legacy_labels = sorted(legacy_catalog.keys())
                default_legacy = edited_file_default if edited_file_default in legacy_labels else legacy_labels[0]
                selected_legacy = st.selectbox("Legacy edited file", legacy_labels, index=legacy_labels.index(default_legacy))
                selected_input_csv = legacy_catalog[selected_legacy]
                edited_file_label = selected_legacy
        else:
            selected_input_csv = str(DATASET_OPTIONS[dataset_label])

        selected_df = load_graph_dataframe(selected_input_csv, dataset_label)
        accepted_only = st.toggle("Accepted only when available", value=accepted_default)

        paper_options = ["All papers"] + sorted(selected_df["paper_title"].dropna().unique().tolist())
        if paper_default not in paper_options:
            paper_default = "All papers"
        paper_title = st.selectbox("Paper", paper_options, index=paper_options.index(paper_default))

        predicate_options = sorted(selected_df["predicate"].dropna().unique().tolist())
        predicates = st.multiselect(
            "Predicates",
            predicate_options,
            default=[item for item in predicate_defaults if item in predicate_options],
        )

        subject_type_options = sorted(selected_df["subject_type"].dropna().unique().tolist())
        subject_types = st.multiselect(
            "Subject types",
            subject_type_options,
            default=[item for item in subject_type_defaults if item in subject_type_options],
        )

        object_type_options = sorted(selected_df["object_type"].dropna().unique().tolist())
        object_types = st.multiselect(
            "Object types",
            object_type_options,
            default=[item for item in object_type_defaults if item in object_type_options],
        )

        relation_origin_options = sorted(selected_df["relation_origin"].dropna().unique().tolist())
        relation_origins = st.multiselect(
            "Relation origin",
            relation_origin_options,
            default=[item for item in relation_origin_defaults if item in relation_origin_options],
        )

        search_text = st.text_input(
            "Search text",
            value=search_default,
            placeholder="Filter by subject, object, or evidence text",
        )

        max_nodes = st.slider("Max nodes", min_value=10, max_value=300, value=min(max(max_nodes_default, 10), 300), step=10)
        max_edges = st.slider("Max edges", min_value=20, max_value=1000, value=min(max(max_edges_default, 20), 1000), step=20)

    filtered_df = filter_dataframe(
        selected_df,
        paper_title=paper_title,
        predicates=predicates,
        subject_types=subject_types,
        object_types=object_types,
        relation_origins=relation_origins,
        search_text=search_text,
        accepted_only=accepted_only,
    )

    metrics = st.columns(5)
    metrics[0].metric("Corpus papers", f"{summary.get('paper_count', 0):,}")
    metrics[1].metric("Schema rules", f"{summary.get('rule_count', 0):,}")
    metrics[2].metric("Current rows", f"{len(filtered_df):,}")
    metrics[3].metric("Mapped mentions", f"{summary.get('mapped_mention_count', 0):,}")
    metrics[4].metric("Candidate rows", f"{summary.get('relation_candidate_count', 0):,}")

    render_dataset_panel(
        dataset_label,
        filtered_df,
        max_nodes=max_nodes,
        max_edges=max_edges,
        input_csv=selected_input_csv,
        paper_title=paper_title,
        predicates=predicates,
        height=DEFAULT_HEIGHT,
    )

    # st.markdown("### Paper Editing Workspace")
    # if paper_title == "All papers":
    #     st.info("Select a specific paper in the sidebar to view paper text, highlighted relations, and edit the extracted graph.")
    # else:
    #     paper_match = paper_index.loc[paper_index["title"] == paper_title]
    #     if paper_match.empty:
    #         st.warning("Selected paper could not be found in the paper index.")
    #     else:
    #         paper_row = paper_match.iloc[0]
    #         paper_id = str(paper_row["paper_id"])
    #         paper_sentences = sentence_index.loc[sentence_index["paper_id"] == paper_id].copy()
    #         paper_base_df = selected_df.loc[selected_df["paper_title"] == paper_title].copy()
    #         if accepted_only and "accepted" in paper_base_df.columns:
    #             paper_base_df = paper_base_df[paper_base_df["accepted"] == True]

    #         session_key = f"editable_relations::{dataset_label}::{paper_id}"
    #         if session_key not in st.session_state:
    #             st.session_state[session_key] = init_editable_relations(
    #                 dataset_label,
    #                 paper_id,
    #                 paper_title,
    #                 str(paper_row["doi"]),
    #                 paper_base_df,
    #                 paper_sentences,
    #             )

    #         delete_rel = _first_query_param("delete_rel")
    #         delete_session = _first_query_param("delete_session")
    #         if delete_rel and delete_session == session_key:
    #             updated = st.session_state[session_key].loc[
    #                 st.session_state[session_key]["relation_id"] != delete_rel
    #             ].reset_index(drop=True)
    #             st.session_state[session_key] = updated
    #             clear_delete_query_params()
    #             st.rerun()

    #         editable_df = st.session_state[session_key]
    #         ui_state = {
    #             "dataset": dataset_label,
    #             "accepted": accepted_only,
    #             "paper": paper_title,
    #             "predicates": predicates,
    #             "subject_types": subject_types,
    #             "object_types": object_types,
    #             "relation_origins": relation_origins,
    #             "search_text": search_text,
    #             "max_nodes": max_nodes,
    #             "max_edges": max_edges,
    #         }

    #         render_sentence_relation_workspace(
    #             dataset_label,
    #             paper_row,
    #             paper_sentences,
    #             editable_df,
    #             session_key,
    #             allowed_predicates,
    #             ui_state,
    #         )

    #         st.markdown("#### Current editable relations")
    #         st.dataframe(editable_df, width="stretch", height=320)

    #         save_col, download_col = st.columns(2)
    #         with save_col:
    #             if st.button(
    #                 "Save modified relations",
    #                 key=f"save_relations_button::{session_key}",
    #                 type="primary",
    #             ):
    #                 output_path = save_editable_relations(dataset_label, paper_id, editable_df)
    #                 st.success(f"Saved editable graph file to {output_path}")
    #         with download_col:
    #             st.download_button(
    #                 "Download modified relations CSV",
    #                 editable_df.to_csv(index=False).encode("utf-8"),
    #                 file_name=f"{dataset_label.casefold().replace(' ', '_')}_{paper_id}_edited_graph.csv",
    #                 mime="text/csv",
    #                 key=f"download_edited_relations::{session_key}",
    #             )

    st.markdown("### Explorer Summary")
    st.json(
        {
            "schema_summary": summary,
            "dataset": dataset_label,
            "edited_file": edited_file_label if dataset_label == "Edited graph" else None,
            "accepted_only": accepted_only,
            "paper": paper_title,
            "predicates": predicates,
            "subject_types": subject_types,
            "object_types": object_types,
            "relation_origins": relation_origins,
            "search_text": search_text,
        }
    )


if __name__ == "__main__":
    main()
