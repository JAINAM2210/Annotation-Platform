# =========================================================
# IMPORTS
# =========================================================
import streamlit as st
import numpy as np
import networkx as nx
from sentence_transformers import SentenceTransformer
import google.generativeai as genai
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

def load_triples_from_csv(file_path):
    df = pd.read_csv(file_path)

    triples = []

    for _, row in df.iterrows():
        triples.append((
            row["source"],
            row["relation"],
            row["target"],
            row["source_type"],
            row["target_type"]
        ))

    return triples


all_triples = load_triples_from_csv(DATA_DIR / "all_triples.csv")


# =========================================================
# CONFIG
# =========================================================
FILE_PATH = DATA_DIR / "dz2bm3yl.txt"
from together import Together

client = Together(api_key="tgp_v1_ZB25JjwbAPI9x_jz4VUsjxDhkBkqg-za221-sa7jDSU")
MODEL_NAME = "meta-llama/Llama-3.3-70B-Instruct-Turbo"

# =========================================================
# LOAD DATA (BIO → sentences)
# =========================================================
def bio_to_sentences(file_path):
    sentences = []
    current = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                if current:
                    sentences.append(" ".join(current))
                    current = []
                continue

            token = line.split()[0]
            current.append(token)

    return sentences


# =========================================================
# CHUNKING
# =========================================================
def chunk_text(sentences, chunk_size=3, overlap=1):
    chunks = []
    step = chunk_size - overlap

    for i in range(0, len(sentences), step):
        chunks.append(" ".join(sentences[i:i+chunk_size]))

    return chunks


# =========================================================
# NORMAL RAG SETUP
# =========================================================
@st.cache_resource
def setup_normal_rag():
    sentences = bio_to_sentences(FILE_PATH)
    chunks = chunk_text(sentences, chunk_size=3, overlap=1)

    model = SentenceTransformer('all-MiniLM-L6-v2')
    embeddings = model.encode(chunks)

    return model, chunks, embeddings


model, chunks, chunk_embeddings = setup_normal_rag()


# =========================================================
# NORMAL RAG FUNCTIONS
# =========================================================
def retrieve_chunks(query, top_k=5):
    query_emb = model.encode(query)
    scores = np.dot(chunk_embeddings, query_emb)
    top_indices = np.argsort(scores)[-top_k:][::-1]
    return [chunks[i] for i in top_indices]


def answer_rag(query, retrieved_chunks):
    context = "\n\n".join(retrieved_chunks)

    prompt = f"""
        You are a scientific assistant.

        Use ONLY the context below to answer.

        Context:
        {context}

        Question:
        {query}

        If answer not found, say "Not found".
        """

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.2
    )

    return response.choices[0].message.content


def normal_rag(query):
    retrieved = retrieve_chunks(query)
    return answer_rag(query, retrieved)


# =========================================================
# KG-RAG SETUP (build graph from triples)
# =========================================================

# ⚠️ Replace this with your actual triples if needed
# Example placeholder:
# all_triples = []  # <-- IMPORTANT: load your triples here


def build_graph(triples):
    G = nx.DiGraph()

    for (src, rel, tgt, src_type, tgt_type) in triples:
        G.add_node(src, type=src_type)
        G.add_node(tgt, type=tgt_type)
        G.add_edge(src, tgt, label=rel)

    return G


G = build_graph(all_triples)


# =========================================================
# KG-RAG FUNCTIONS
# =========================================================
def semantic_search(query, top_k=5):
    query_emb = model.encode(query)

    scores = {
        node: np.dot(query_emb, model.encode(node))
        for node in G.nodes
    }

    ranked = sorted(scores, key=scores.get, reverse=True)
    return ranked[:top_k]


def get_subgraph(nodes, depth=2):
    sub_nodes = set(nodes)

    for _ in range(depth):
        for n in list(sub_nodes):
            sub_nodes.update(G.successors(n))
            sub_nodes.update(G.predecessors(n))

    return G.subgraph(sub_nodes)


def graph_to_text(subgraph):
    context = []

    for u, v, data in subgraph.edges(data=True):
        context.append(f"{u} {data['label']} {v}")

    return "\n".join(context)


def kg_rag(query):
    if len(G.nodes) == 0:
        return "⚠️ Graph not loaded."

    nodes = semantic_search(query)
    subgraph = get_subgraph(nodes)
    context = graph_to_text(subgraph)

    prompt = f"""
        You are a scientific assistant.

        Use ONLY the knowledge graph below.

        Knowledge Graph:
        {context}

        Question:
        {query}

        If answer not found, say "Not found".
        """

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.5
    )

    return response.choices[0].message.content


# =========================================================
# STREAMLIT UI
# =========================================================
st.set_page_config(page_title="RAG System", layout="wide")

st.title("🔬 RAG vs KG-RAG Demo")

mode = st.sidebar.selectbox(
    "Choose Mode",
    ["Normal RAG", "KG-RAG", "Compare Both"]
)

query = st.text_input("Ask a question:")


# =========================================================
# RUN
# =========================================================
if st.button("Get Answer"):

    if not query:
        st.warning("Please enter a question")

    else:
        with st.spinner("Thinking..."):

            if mode == "Normal RAG":
                answer = normal_rag(query)
                st.success("Answer:")
                st.write(answer)

            elif mode == "KG-RAG":
                answer = kg_rag(query)
                st.success("Answer:")
                st.write(answer)

            else:
                col1, col2 = st.columns(2)

                normal_ans = normal_rag(query)
                kg_ans = kg_rag(query)

                with col1:
                    st.subheader("Normal RAG")
                    st.write(normal_ans)

                with col2:
                    st.subheader("KG-RAG")
                    st.write(kg_ans)
