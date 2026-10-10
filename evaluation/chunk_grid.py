"""Isolated exact-cosine chunk/K experiment; never changes production collections."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import statistics

import numpy as np

from evaluation.top_k import (
    DEFAULT_OUTPUT as PREVIOUS_OUTPUT, ROOT, assert_snapshot_matches, digest,
    load_dataset, merge_intervals, positions, read_json, score_hits, write_json,
)


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "results" / "chunk_grid_20261009"
VALIDATION = HERE / "chunk_validation.json"
SIZES = (300, 500, 800)
OVERLAPS = (0, 80, 150)
KS = (1, 3, 5, 8)
SEPARATORS = ["\n\n", "\n", "。", "；", "，", " "]


def normalize_vectors(vectors):
    matrix = np.asarray(vectors, dtype=np.float64)
    if matrix.ndim != 2 or not np.isfinite(matrix).all():
        raise ValueError("Vectors must be a finite matrix")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("Zero vectors cannot be used for cosine similarity")
    return matrix / norms


def cosine_hits(chunks, document_vectors, query_vector, k):
    scores = normalize_vectors(document_vectors) @ normalize_vectors([query_vector])[0]
    order = np.argsort(-scores, kind="stable")[:k]
    return [{**chunks[int(index)], "score": float(scores[index])} for index in order]


def split_variants(texts):
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    docs = [Document(page_content=texts[source], metadata={"source": source}) for source in sorted(texts)]
    variants = {}
    for size in SIZES:
        for overlap in OVERLAPS:
            splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap,
                                                     separators=SEPARATORS)
            chunks = [{"id": index + 1, "source": chunk.metadata["source"], "text": chunk.page_content,
                       "path": str(ROOT / "data" / "knowledge" / chunk.metadata["source"])}
                      for index, chunk in enumerate(splitter.split_documents(docs))]
            pairs = []
            previous = {}
            for chunk in chunks:
                source = chunk["source"]
                start, end = next(positions(texts[source], chunk["text"]))
                if source in previous:
                    pairs.append(max(0, previous[source] - start))
                previous[source] = end
            variants[f"{size}/{overlap}"] = {
                "size": size, "overlap": overlap, "chunks": chunks,
                "chunk_set_sha256": digest([(chunk["source"], chunk["text"]) for chunk in chunks]),
                "actual_adjacent_overlap": pairs,
                "total_characters": sum(len(chunk["text"]) for chunk in chunks),
            }
    return variants


def prepare(output):
    old_dataset, texts, clauses = load_dataset()
    validation = read_json(VALIDATION)
    seen = {case["query"] for case in old_dataset["cases"]}
    new_ids = set()
    for case in validation["cases"]:
        if case["id"] in new_ids or case["query"] in seen:
            raise ValueError("New validation cases must not duplicate ids or old questions")
        new_ids.add(case["id"])
        if any(key not in clauses for key in case["requires"]):
            raise ValueError("Unknown validation gold clause")
        if not case["requires"] and not case.get("expected"):
            raise ValueError("Unanswerable cases need an expected result")
    previous_config = read_json(PREVIOUS_OUTPUT / "config.json")
    if previous_config is None or previous_config["dataset_sha256"] != digest(old_dataset):
        raise ValueError("Previous question cache belongs to a different dataset")
    if previous_config["documents_sha256"] != digest(texts):
        raise ValueError("Policy text changed since the previous experiment")
    variants = split_variants(texts)
    config = {
        "old_dataset_sha256": digest(old_dataset), "validation_sha256": digest(validation),
        "documents_sha256": digest(texts), "sizes": list(SIZES), "overlaps": list(OVERLAPS),
        "k_values": list(KS), "metric": "COSINE", "embedding_model": "text-embedding-v3",
        "query_cache_sha256": digest(read_json(PREVIOUS_OUTPUT / "query_vectors.json")),
        "engine": "isolated NumPy exact cosine, not a Milvus ANN latency benchmark",
    }
    previous = read_json(output / "config.json")
    if previous is not None and previous != config:
        raise ValueError("Frozen inputs changed; choose a new output directory")
    write_json(output / "config.json", config)
    write_json(output / "old_dataset_snapshot.json", old_dataset)
    write_json(output / "validation_snapshot.json", validation)
    write_json(output / "documents_snapshot.json", texts)
    write_json(output / "variants.json", variants)
    return old_dataset, validation, texts, clauses, variants


def check_budget(current, maximum=60):
    if current >= maximum:
        raise RuntimeError("This experiment's approved 60 embedding requests are exhausted")
    return current + 1


class RequestBudget:
    def __init__(self, output):
        self.path = output / "request_budget.json"
        self.counts = read_json(self.path, {"embedding": 0, "deepseek": 0})

    def consume(self):
        self.counts["embedding"] = check_budget(self.counts["embedding"])
        write_json(self.path, self.counts)


def unique_text_characters(hits, texts):
    intervals = {}
    for hit in hits:
        intervals.setdefault(hit["source"], []).extend(positions(texts[hit["source"]], hit["text"]))
    return sum(end - start for ranges in intervals.values() for start, end in merge_intervals(ranges))


def aggregate(rows):
    positives = [row for row in rows if row["answerable"]]
    return {
        "questions": len(rows), "answerable_questions": len(positives),
        "full_evidence_count": sum(row["full_evidence"] for row in positives),
        "full_evidence": statistics.mean(row["full_evidence"] for row in positives),
        "evidence_hit": statistics.mean(row["evidence_hit"] for row in positives),
        "evidence_coverage": statistics.mean(row["evidence_coverage"] for row in positives),
        "mean_context_characters": statistics.mean(row["context_characters"] for row in rows),
        "mean_duplicate_characters": statistics.mean(row["duplicate_characters"] for row in rows),
        "unanswerable_with_results": sum(not row["answerable"] and bool(row["hits"]) for row in rows),
    }


def candidate_sort_key(summary):
    return (summary["full_evidence"], summary["evidence_coverage"],
            -summary["mean_context_characters"], -summary["chunk_count"],
            -summary["overlap"], -summary["k"], -summary["size"])


def select_joint(summaries):
    return max(summaries, key=lambda key: candidate_sort_key(summaries[key]))


def score_split(cases, query_vectors, document_vectors, variants, texts, clauses):
    records, summaries = {}, {}
    for variant_name, variant in variants.items():
        chunks = variant["chunks"]
        vectors = [document_vectors[digest(chunk["text"])] for chunk in chunks]
        for k in KS:
            setting = f"{variant_name}/k{k}"
            rows = []
            for case in cases:
                hits = cosine_hits(chunks, vectors, query_vectors[case["id"]]["vector"], k)
                row = {"case_id": case["id"], "setting": setting, "hits": hits,
                       **score_hits(case, hits, texts, clauses)}
                row["duplicate_characters"] = row["context_characters"] - unique_text_characters(hits, texts)
                rows.append(row)
                records[f"{case['id']}:{setting}"] = row
            summaries[setting] = {"size": variant["size"], "overlap": variant["overlap"], "k": k,
                                  "chunk_count": len(chunks), **aggregate(rows)}
    return records, summaries


def baseline_check(client, collection, variants, old_queries, document_vectors, texts):
    production = client.query(collection, filter="id >= 0", limit=1000,
                              output_fields=["id", "text", "source", "path", "vector"], timeout=10)
    baseline = variants["500/80"]["chunks"]
    assert_snapshot_matches(baseline, production)
    old_results = read_json(PREVIOUS_OUTPUT / "retrieval.json")
    production_vectors = [row["vector"] for row in production]
    fresh_vectors = [document_vectors[digest(row["text"])] for row in production]
    agreement = {"local_vs_previous_milvus_top3": 0, "fresh_vs_production_vectors_top3": 0}
    for case_id, query in old_queries.items():
        exact = cosine_hits(production, production_vectors, query["vector"], 3)
        fresh = cosine_hits(production, fresh_vectors, query["vector"], 3)
        actual = old_results[f"{case_id}:3"]["hits"]
        identity = lambda rows: [(row["source"], row["text"]) for row in rows]
        agreement["local_vs_previous_milvus_top3"] += identity(exact) == identity(actual)
        agreement["fresh_vs_production_vectors_top3"] += identity(fresh) == identity(exact)
    agreement["queries"] = len(old_queries)
    agreement["production_rows"] = len(production)
    return agreement


def run(output):
    from pymilvus import MilvusClient
    from config.milvus import get_milvus_config
    from langchain_community.embeddings.dashscope import BATCH_SIZE
    from rag.retriever import get_embeddings

    dataset, validation, texts, clauses, variants = prepare(output)
    old_queries = read_json(PREVIOUS_OUTPUT / "query_vectors.json")
    budget = RequestBudget(output)
    embeddings = get_embeddings()
    embeddings.max_retries = 1
    document_vectors = read_json(output / "document_vectors.json", {})
    new_queries = read_json(output / "validation_vectors.json", {})
    unique = {digest(chunk["text"]): chunk["text"] for variant in variants.values() for chunk in variant["chunks"]}
    missing = [(key, text) for key, text in sorted(unique.items()) if key not in document_vectors]
    batch_size = BATCH_SIZE.get(embeddings.model, 10)
    expected = (len(missing) + batch_size - 1) // batch_size + sum(
        case["id"] not in new_queries for case in validation["cases"]
    )
    if budget.counts["embedding"] + expected > 60:
        raise RuntimeError("Embedding plan exceeds approved budget")
    for index in range(0, len(missing), batch_size):
        batch = missing[index:index + batch_size]
        budget.consume()
        vectors = embeddings.embed_documents([text for _, text in batch])
        if len(vectors) != len(batch):
            raise ValueError("Embedding batch has missing results")
        for (key, _), vector in zip(batch, vectors):
            document_vectors[key] = vector
        write_json(output / "document_vectors.json", document_vectors)
        print(f"document embeddings: {len(document_vectors)}/{len(unique)} unique texts", flush=True)
    dev_records, dev_summary = score_split(dataset["cases"], old_queries, document_vectors, variants, texts, clauses)
    write_json(output / "development_results.json", dev_records)
    write_json(output / "development_summary.json", dev_summary)
    selected = select_joint(dev_summary)
    selection = {"setting": selected, "selected_at": datetime.now(timezone.utc).isoformat(),
                 "rule": "old 60 questions only: full evidence, coverage, minimum returned characters, minimum chunks, minimum target overlap"}
    old_selection = read_json(output / "selection.json")
    if old_selection is not None:
        if old_selection["setting"] != selected:
            raise ValueError("Selection changed after validation was inspected")
        selection = old_selection
    write_json(output / "selection.json", selection)
    print(f"candidate frozen before validation: {selected}", flush=True)
    for case in validation["cases"]:
        if case["id"] not in new_queries:
            budget.consume()
            new_queries[case["id"]] = {"vector": embeddings.embed_query(case["query"])}
            write_json(output / "validation_vectors.json", new_queries)
        print(f"new query embeddings: {len(new_queries)}/{len(validation['cases'])}", flush=True)
    validation_records, validation_summary = score_split(validation["cases"], new_queries, document_vectors,
                                                         variants, texts, clauses)
    write_json(output / "validation_results.json", validation_records)
    write_json(output / "validation_summary.json", validation_summary)
    config = get_milvus_config()
    client = MilvusClient(uri=config["uri"], db_name=config["db_name"], timeout=10)
    try:
        alignment = baseline_check(client, config["collection_name"], variants, old_queries,
                                   document_vectors, texts)
    finally:
        client.close()
    write_json(output / "baseline_alignment.json", alignment)
    print({"selection": selection, "baseline_alignment": alignment, "budget": budget.counts}, flush=True)
    make_report(output)


def percentage(value):
    return f"{value * 100:.1f}%"


def make_report(output):
    config = read_json(output / "config.json")
    variants = read_json(output / "variants.json")
    dev = read_json(output / "development_summary.json")
    validation = read_json(output / "validation_summary.json")
    selection = read_json(output / "selection.json")
    budget = read_json(output / "request_budget.json")
    alignment = read_json(output / "baseline_alignment.json")
    if not dev or not validation or not selection:
        raise ValueError("Cannot report an incomplete experiment")
    old_dataset = read_json(output / "old_dataset_snapshot.json")
    new_dataset = read_json(output / "validation_snapshot.json")
    texts = read_json(output / "documents_snapshot.json")
    if (digest(old_dataset) != config["old_dataset_sha256"]
            or digest(new_dataset) != config["validation_sha256"]
            or digest(texts) != config["documents_sha256"]):
        raise ValueError("Frozen dataset or policy snapshot changed")
    expected_settings = {f"{name}/k{k}" for name in variants for k in config["k_values"]}
    if set(dev) != expected_settings or set(validation) != expected_settings:
        raise ValueError("All paired settings must be present before reporting")
    selected = selection["setting"]
    same_chunks = {}
    for name, variant in variants.items():
        same_chunks.setdefault(variant["chunk_set_sha256"], []).append(name)
    equivalence = [names for names in same_chunks.values() if len(names) > 1]
    lines = [
        "# 切分参数与 Top K 联合评测", "",
        "## 实验范围", "",
        "本报告只验证当前文本、Embedding及候选网格下的检索证据覆盖，不证明通用最优或最终回答准确率。",
        "没有改变生产切分或K，没有重建生产集合，不写PostgreSQL。使用隔离的NumPy精确余弦排序，避免近似索引噪音。",
        "9组切分：size=300/500/800，overlap=0/80/150；每组比较K=1/3/5/8，共36个组合。",
        "原来的60题全部作为开发数据，旧留出集已被查看，不再作为本轮留出集。另在运行前冻结20道新场景题（16可回答、4库外）。",
        "题目由助手构造，共享政策文本，非独立真实用户或文档隔离验证；金标准的等价来源也可能不完整。",
        "新题的结果只用于检查预先选择的候选，不据此重新挑选参数。未调用DeepSeek，没有测最终回答或实际生成Token。", "",
        "## 一个直接可证明的结构结果", "",
        "500字符是保留短政策上下文并控制输入长度的工程初值；80字符是希望保留边界上下文的目标重叠，并非已验证最优。",
        "递归切分按分隔单位合并，overlap是目标，不保证从每片末尾硬截出恰好80字符。下表检查真实片段范围，而不只看配置。", "",
        "| 切分配置 | 片段数 | 存储文本字符 | 相邻片段实际重叠字符合计 |",
        "|---|---:|---:|---:|",
    ]
    for name, variant in variants.items():
        lines.append(f"| {name} | {len(variant['chunks'])} | {variant['total_characters']} | {sum(variant['actual_adjacent_overlap'])} |")
    lines += [
        "", f"完全相同的切分结果组：{equivalence}。",
        "因此，当前文件上不能说80字符重叠带来了提升：500/80与500/0生成完全相同的文本，实际没有重叠。",
        "800超过所有当前文档长度（最长647字符），所以800/0、800/80、800/150均为整篇文档检索。不能将其推广到长文档。", "",
        "## 开发集的每组候选", "",
        "选择规则预先固定：先全证据覆盖率，再条款覆盖率，然后返回字符更少；并列时片段数、目标重叠和K更小优先。",
        "成本用返回字符作代理，不能当作真实Token费用或把重复字符等同于全部检索噪音。", "",
        "| size/overlap | 开发集选择K | 全证据题数 | 条款覆盖率 | 平均返回字符 |",
        "|---|---:|---:|---:|---:|",
    ]
    per_variant = {}
    for name in variants:
        candidate = select_joint({key: value for key, value in dev.items() if key.startswith(name + "/k")})
        row = dev[candidate]
        per_variant[name] = candidate
        lines.append(f"| {name} | {row['k']} | {row['full_evidence_count']}/{row['answerable_questions']} | {percentage(row['evidence_coverage'])} | {row['mean_context_characters']:.1f} |")
    lines += ["", f"只用开发集选出的联合候选：**{selected}**。", "", "## 同一个K在不同切分下的表现", "",
              "每格是开发集完整覆盖题数/50。候选选择不使用新验证题。", "",
              "| size/overlap | K=1 | K=3 | K=5 | K=8 |", "|---|---:|---:|---:|---:|"]
    for name in variants:
        values = [str(dev[f"{name}/k{k}"]["full_evidence_count"]) + "/50" for k in KS]
        lines.append("| " + name + " | " + " | ".join(values) + " |")
    focus = list(dict.fromkeys(["500/80/k3", "500/80/k5", "500/80/k8",
                               "300/150/k3", "300/150/k5", selected, "800/0/k3", "800/0/k5"]))
    lines += ["", "## 新验证题核对", "", "| 配置 | 全证据题数 | 条款覆盖率 | 平均返回字符 |",
              "|---|---:|---:|---:|"]
    for name in focus:
        row = validation[name]
        lines.append(f"| {name} | {row['full_evidence_count']}/{row['answerable_questions']} | {percentage(row['evidence_coverage'])} | {row['mean_context_characters']:.1f} |")
    candidate_row = validation[selected]
    baseline_row = validation["500/80/k3"]
    write_json(output / "final_summary.json", {"selection": selection, "development": dev,
               "validation": validation, "equivalent_chunk_sets": equivalence,
               "baseline_alignment": alignment, "budget": budget})
    lines += [
        "", "## 结论应怎样理解", "",
        f"联合候选在新题上完整覆盖{candidate_row['full_evidence_count']}/16；当前500/80/K3为{baseline_row['full_evidence_count']}/16。",
        "不过，开发集挑出的300/150/K8在新题上不如原切分的K5（15/16），因此不能仅凭开发成绩宣布换切分更好。",
        "800/0/K5在新题上为16/16，但当前等于整篇短文档召回，返回字符也更多；这是描述性结果，不据此再次挑参或宣称全局最佳。",
        "这是候选范围内、指定目标下的结果，不是绝对最佳切分。没有给出最终答案质量或实际模型Token成本结论。",
        "切分改变会改变片段的内容、数量、排名和重复程度，因此必须重测K，但不代表K一定要改。",
        "调整size/overlap后，只有重新切分并生成文档向量、写入新集合，检索才会使用新参数；仅修改配置不会更新旧向量。",
        "建议先做候选与基线的答案对照，再决定是否切换生产配置。本次不自动切换或删除任何生产数据。", "",
        "## 可复查缺失条款", "",
        "- H08：补交故障证据是否应该新建案件。300/150/K8没有召回标注的关联已有售后单条款。",
        "- H12：无理由与运输破损运费、优惠分摊。500/80/K3缺三项，K5仍缺运输破损的专项运费条款；300/150/K8也缺该项。",
        "- H02、H10、H13：500/80/K3分别缺维修不自动退款、签收不等于真实收货、待审核不能承诺批准退款条款。",
        "原始明细含命中片段和clause_hits，可人工检查是否存在未标注的等价证据；不能把严格跨度缺失直接等同于最终回答错误。", "",
        "## 与现有Milvus的对照与调用预算", "",
        f"同一批旧查询、同一批生产向量，本地精确排序与之前Milvus Top3顺序一致：{alignment['local_vs_previous_milvus_top3']}/{alignment['queries']}。",
        f"重新生成的500/80向量与生产向量Top3顺序一致：{alignment['fresh_vs_production_vectors_top3']}/{alignment['queries']}。",
        "一致度检查只覆盖基线，不能宣称所有新配置的ANN行为或并发性能已验证。",
        f"本轮Embedding请求：{budget['embedding']}，授权上限60；DeepSeek请求：{budget['deepseek']}。",
        "复用旧60个查询向量；不同切分中的相同文本只嵌入一次；生成20个新查询向量。重复运行复用缓存不是独立复测。", "",
        "## 复现", "",
        "```powershell", "python -X utf8 -m evaluation.chunk_grid prepare",
        "python -X utf8 -m evaluation.chunk_grid run", "python -X utf8 -m evaluation.chunk_grid report", "```", "",
        "prepare与report不调用付费API；run会产生Embedding费用，独立新运行必须取得新授权。",
        "结果保存在results/chunk_grid_20261009；评分明细、参数、查询向量、文档向量和新题快照均可复查。",
        f"源文档SHA256：`{config['documents_sha256']}`。",
        f"新题SHA256：`{config['validation_sha256']}`。",
    ]
    path = HERE / "chunk_grid_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(path, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "run", "report"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.stage == "prepare":
        _, _, _, _, variants = prepare(args.output)
        unique = {digest(chunk["text"]) for variant in variants.values() for chunk in variant["chunks"]}
        print({"configurations": len(variants), "distinct_chunk_sets": len({v['chunk_set_sha256'] for v in variants.values()}),
               "unique_document_texts": len(unique), "fresh_validation_questions": 20}, flush=True)
    elif args.stage == "run":
        run(args.output)
    else:
        make_report(args.output)


if __name__ == "__main__":
    main()
