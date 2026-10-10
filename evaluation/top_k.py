"""Read-only Top K experiment; never writes to Milvus or PostgreSQL."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
from time import perf_counter


ROOT = Path(__file__).resolve().parent.parent
DATASET = Path(__file__).with_name("top_k_dataset.json")
DEFAULT_OUTPUT = Path(__file__).with_name("results") / "top_k_20261009"
KS = (1, 3, 5, 8)


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def load_dataset(path=DATASET):
    dataset = read_json(path)
    texts = {}
    for alias, filename in dataset["documents"].items():
        if Path(filename).name != filename:
            raise ValueError("Document names must not contain directories")
        texts[filename] = (ROOT / "data" / "knowledge" / filename).read_text(encoding="utf-8")
    clauses = {}
    for key, clause in dataset["clauses"].items():
        alternatives = []
        for evidence in clause["evidence"]:
            filename = dataset["documents"][evidence["source"]]
            quote = evidence["quote"]
            if not quote or quote not in texts[filename]:
                raise ValueError(f"Gold evidence is absent from source: {key}")
            alternatives.append({"source": filename, "quote": quote})
        clauses[key] = {"label": clause["label"], "evidence": alternatives}
    ids, groups = set(), {}
    for case in dataset["cases"]:
        if case["id"] in ids:
            raise ValueError("Duplicate case id")
        ids.add(case["id"])
        if case["split"] not in ("dev", "test"):
            raise ValueError("Unknown split")
        old_split = groups.setdefault(case["group"], case["split"])
        if old_split != case["split"]:
            raise ValueError("A question group is shared across splits")
        if any(key not in clauses for key in case["requires"]):
            raise ValueError("Unknown gold clause")
        if not case["requires"] and not case.get("expected"):
            raise ValueError("Unanswerable cases need an expected abstention")
    return dataset, texts, clauses


def merge_intervals(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def covered(start, end, intervals):
    return any(left <= start and right >= end for left, right in merge_intervals(intervals))


def positions(text, part):
    start = text.find(part)
    while start >= 0:
        yield start, start + len(part)
        start = text.find(part, start + 1)


def score_hits(case, hits, texts, clauses):
    intervals = {}
    for hit in hits:
        source = hit["source"]
        if source not in texts or hit["text"] not in texts[source]:
            raise ValueError("Retrieved text differs from the frozen local source")
        intervals.setdefault(source, []).extend(positions(texts[source], hit["text"]))
    clause_hits = {}
    relevant_sources = set()
    for key in case["requires"]:
        evidence = clauses[key]["evidence"]
        relevant_sources.update(item["source"] for item in evidence)
        # Union source ranges, so a clause spanning two returned chunks can count.
        clause_hits[key] = any(
            any(covered(start, end, intervals.get(item["source"], []))
                for start, end in positions(texts[item["source"]], item["quote"]))
            for item in evidence
        )
    required_count = len(clause_hits)
    return {
        "answerable": bool(required_count),
        "source_hit": any(hit["source"] in relevant_sources for hit in hits) if required_count else None,
        "evidence_hit": any(clause_hits.values()) if required_count else None,
        "evidence_coverage": sum(clause_hits.values()) / required_count if required_count else None,
        "full_evidence": all(clause_hits.values()) if required_count else None,
        "source_precision_proxy": (
            sum(hit["source"] in relevant_sources for hit in hits) / len(hits)
            if required_count and hits else None
        ),
        "clause_hits": clause_hits,
        "context_characters": sum(len(hit["text"]) for hit in hits),
    }


def assert_snapshot_matches(local_chunks, remote_rows):
    local = Counter((chunk["source"], chunk["text"]) for chunk in local_chunks)
    remote = Counter((row["source"], row["text"]) for row in remote_rows)
    if local != remote:
        raise ValueError("Milvus content is stale or different; evaluation will not rebuild it")


def summarize(dataset, records):
    summary = {}
    for split in ("dev", "test"):
        cases = [case for case in dataset["cases"] if case["split"] == split]
        split_summary = {}
        for k in KS:
            rows = [records.get(f"{case['id']}:{k}") for case in cases]
            if any(row is None for row in rows):
                raise ValueError("Cannot summarize an incomplete, unpaired experiment")
            positives = [row for row in rows if row["answerable"]]
            metrics = {"questions": len(rows), "answerable_questions": len(positives)}
            for name in ("source_hit", "evidence_hit", "evidence_coverage", "full_evidence", "source_precision_proxy"):
                values = [row[name] for row in positives if row[name] is not None]
                metrics[name] = statistics.mean(values) if values else None
            metrics["mean_context_characters"] = statistics.mean(row["context_characters"] for row in rows)
            metrics["median_search_ms"] = statistics.median(row["search_ms"] for row in rows)
            metrics["p95_search_ms"] = sorted(row["search_ms"] for row in rows)[max(0, int(0.95 * len(rows)) - 1)]
            metrics["unanswerable_with_results"] = sum(not row["answerable"] and bool(row["hits"]) for row in rows)
            split_summary[str(k)] = metrics
        summary[split] = split_summary
    return summary


def select_candidate(summary):
    alternatives = [k for k in KS if k != 3]
    return max(alternatives, key=lambda k: (
        summary["dev"][str(k)]["full_evidence"],
        summary["dev"][str(k)]["evidence_coverage"],
        -summary["dev"][str(k)]["mean_context_characters"],
        -k,
    ))


class Budget:
    def __init__(self, path):
        self.path = path
        self.data = read_json(path, {"embedding": 0, "deepseek": 0})

    def consume(self, service):
        limit = {"embedding": 80, "deepseek": 40}[service]
        if self.data[service] >= limit:
            raise RuntimeError(f"Approved {service} request budget exhausted")
        self.data[service] += 1
        # Persist before sending; failed calls still consume the approved budget.
        write_json(self.path, self.data)


def freeze_run(output, dataset, texts):
    config = {
        "dataset_sha256": digest(dataset),
        "documents_sha256": digest(texts),
        "k_values": list(KS),
        "embedding_model": "text-embedding-v3",
        "metric": "COSINE",
    }
    old = read_json(output / "config.json")
    if old is not None and old != config:
        raise ValueError("Sources/config changed; choose a new output directory")
    write_json(output / "config.json", config)
    write_json(output / "dataset_snapshot.json", dataset)
    write_json(output / "documents_snapshot.json", texts)
    return config


def retrieve(output):
    from pymilvus import MilvusClient
    from config.milvus import get_milvus_config
    from rag.ingest_knowledge import load_knowledge_documents, split_documents
    from rag.retriever import get_embeddings

    dataset, texts, clauses = load_dataset()
    freeze_run(output, dataset, texts)
    config = get_milvus_config()
    client = MilvusClient(uri=config["uri"], db_name=config["db_name"], timeout=10)
    rows = client.query(config["collection_name"], filter="id >= 0", limit=1000,
                        output_fields=["id", "text", "source", "path"], timeout=10)
    chunks = [{"source": chunk.metadata["source"], "text": chunk.page_content}
              for chunk in split_documents(load_knowledge_documents())]
    assert_snapshot_matches(chunks, rows)
    write_json(output / "collection_snapshot.json", rows)
    embeddings = get_embeddings()
    embeddings.max_retries = 1
    budget = Budget(output / "request_budget.json")
    vectors = read_json(output / "query_vectors.json", {})
    records = read_json(output / "retrieval.json", {})
    warmed = False
    for index, case in enumerate(dataset["cases"]):
        case_id = case["id"]
        if case_id not in vectors:
            budget.consume("embedding")
            started = perf_counter()
            vector = embeddings.embed_query(case["query"])
            vectors[case_id] = {"vector": vector, "embedding_ms": (perf_counter() - started) * 1000}
            write_json(output / "query_vectors.json", vectors)
        vector = vectors[case_id]["vector"]
        if not warmed:
            client.search(config["collection_name"], data=[vector], limit=8,
                          output_fields=["text", "source", "path"],
                          search_params={"metric_type": "COSINE", "params": {}}, timeout=10)
            warmed = True
        order = KS[index % len(KS):] + KS[:index % len(KS)]
        for k in order:
            key = f"{case_id}:{k}"
            if key in records:
                continue
            started = perf_counter()
            result = client.search(config["collection_name"], data=[vector], limit=k,
                                   output_fields=["text", "source", "path"],
                                   search_params={"metric_type": "COSINE", "params": {}}, timeout=10)
            elapsed = (perf_counter() - started) * 1000
            hits = [{"id": item["id"], "score": float(item["distance"]),
                     "text": item["entity"]["text"], "source": item["entity"]["source"],
                     "path": item["entity"].get("path")} for item in result[0]]
            records[key] = {"case_id": case_id, "split": case["split"], "k": k,
                            "search_ms": elapsed, "hits": hits,
                            **score_hits(case, hits, texts, clauses)}
            write_json(output / "retrieval.json", records)
        print(f"retrieval {index + 1}/{len(dataset['cases'])}: {case_id}", flush=True)
    summary = summarize(dataset, records)
    write_json(output / "retrieval_summary.json", summary)
    selection = {"baseline_k": 3, "candidate_k": select_candidate(summary),
                 "rule": "dev only: maximize full_evidence, then coverage, then minimize context characters",
                 "selected_at": datetime.now(timezone.utc).isoformat()}
    old_selection = read_json(output / "selection.json")
    if old_selection:
        if old_selection["candidate_k"] != selection["candidate_k"]:
            raise ValueError("Candidate changed after selection")
        selection = old_selection
    write_json(output / "selection.json", selection)
    client.close()
    print(json.dumps({"selection": selection, "summary": summary}, ensure_ascii=False), flush=True)


class RecordingModel:
    def __init__(self, model, budget):
        self.model = model
        self.budget = budget
        self.response = None
        self.prompt_hash = None
        self.prompt_characters = 0
        self.error = None

    def invoke(self, messages):
        self.budget.consume("deepseek")
        self.prompt_hash = digest(messages)
        self.prompt_characters = sum(len(content) for _, content in messages)
        try:
            self.response = self.model.invoke(messages)
        except Exception as error:
            self.error = {"type": type(error).__name__, "status_code": getattr(error, "status_code", None)}
            raise
        return self.response


def generate(output):
    from config.model import get_model
    import graph.nodes as nodes

    dataset, texts, _ = load_dataset()
    freeze_run(output, dataset, texts)
    selection = read_json(output / "selection.json")
    retrieval = read_json(output / "retrieval.json")
    if not selection or not retrieval:
        raise ValueError("Run retrieval before generation")
    ks = (3, selection["candidate_k"])
    model = get_model()
    model.temperature = 0
    model.max_tokens = 900
    model.max_retries = 0
    model.request_timeout = 45
    model.root_client = model.root_client.with_options(timeout=45, max_retries=0)
    model.client = model.root_client.chat.completions
    settings = {"model": model.model_name, "temperature": 0, "max_tokens": 900,
                "timeout_seconds": 45, "retries": 0,
                "prompt_source_sha256": hashlib.sha256((ROOT / "graph" / "nodes.py").read_bytes()).hexdigest(),
                "scope": "existing knowledge_only_context_node + generate_reply_node; no SQL writes",
                "repeats": 1, "k_values": list(ks)}
    old_settings = read_json(output / "generation_settings.json")
    if old_settings and old_settings != settings:
        raise ValueError("Generation settings changed")
    write_json(output / "generation_settings.json", settings)
    budget = Budget(output / "request_budget.json")
    answers = read_json(output / "answers.json", {})
    cases = [case for case in dataset["cases"] if case.get("generate")]
    if len(cases) * len(ks) > 40:
        raise ValueError("Generation plan exceeds approval")
    original_get_model = nodes.get_model
    try:
        for index, case in enumerate(cases):
            order = ks if index % 2 == 0 else tuple(reversed(ks))
            for k in order:
                key = f"{case['id']}:{k}"
                if key in answers:
                    continue
                row = retrieval[key]
                recorder = RecordingModel(model, budget)
                nodes.get_model = lambda: recorder
                state = nodes.knowledge_only_context_node({
                    "user_message": case["query"], "intent": "knowledge_query",
                    "history_messages": [], "trace_steps": [],
                    "knowledge_result": {"success": bool(row["hits"]), "message": "知识库检索成功",
                                         "data": [{field: hit[field] for field in ("score", "text", "source", "path")}
                                                  for hit in row["hits"]]},
                })
                started = perf_counter()
                result = nodes.generate_reply_node(state)
                usage = recorder.response.usage_metadata if recorder.response is not None else None
                response_metadata = recorder.response.response_metadata if recorder.response is not None else {}
                answers[key] = {"case_id": case["id"], "split": case["split"], "k": k,
                                "query": case["query"], "reply": result["final_reply"],
                                "final_action": result["final_action"], "error": recorder.error,
                                "usage": usage, "finish_reason": response_metadata.get("finish_reason"),
                                "generation_ms": (perf_counter() - started) * 1000,
                                "prompt_sha256": recorder.prompt_hash,
                                "prompt_characters": recorder.prompt_characters}
                write_json(output / "answers.json", answers)
                print(f"generation {len(answers)}/{len(cases) * len(ks)}: {key}; usage={usage}", flush=True)
                if recorder.error:
                    raise RuntimeError(f"Generation stopped after API failure: {recorder.error}")
    finally:
        nodes.get_model = original_get_model
    print("Generation complete; review answers against gold clauses before reporting accuracy.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("validate", "retrieve", "generate"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.stage == "validate":
        dataset, texts, clauses = load_dataset()
        print(json.dumps({"documents": len(texts), "clauses": len(clauses),
                          "cases": len(dataset["cases"]),
                          "splits": dict(Counter(case["split"] for case in dataset["cases"])),
                          "generation_cases": sum(bool(case.get("generate")) for case in dataset["cases"])},
                         ensure_ascii=False))
    elif args.stage == "retrieve":
        retrieve(args.output)
    else:
        generate(args.output)


if __name__ == "__main__":
    main()
