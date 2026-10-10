"""Offline threshold/K sweep over frozen scores; no API or database access."""

import argparse
import math
from pathlib import Path
import statistics

from evaluation.top_k import digest, load_dataset, read_json, score_hits, write_json


HERE = Path(__file__).resolve().parent
CACHE = HERE / "results" / "chunk_grid_20261009"
OUTPUT = HERE / "results" / "threshold_k_20261010"
KS = (1, 3, 5, 8)
THRESHOLDS = (None, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80)
GROUPS = ("all", "old60", "seen20")


def setting_key(k, threshold):
    return f"k{k}/t{'none' if threshold is None else f'{threshold:.2f}'}"


def filter_hits(hits, k, threshold):
    if not isinstance(k, int) or k <= 0:
        raise ValueError("K must be a positive integer")
    if threshold is not None and (not math.isfinite(threshold) or not -1 <= threshold <= 1):
        raise ValueError("A cosine threshold must be finite and between -1 and 1")
    for hit in hits:
        if not math.isfinite(hit["score"]):
            raise ValueError("Cached similarity scores must be finite")
    return [hit for hit in hits[:k] if threshold is None or hit["score"] >= threshold]


def aggregate(rows):
    if not rows:
        raise ValueError("Cannot summarize an empty set")
    positives = [row for row in rows if row["answerable"]]
    negatives = [row for row in rows if not row["answerable"]]
    return {
        "questions": len(rows), "answerable_questions": len(positives),
        "unanswerable_questions": len(negatives),
        "full_evidence_count": sum(row["full_evidence"] for row in positives),
        "full_evidence_rate": statistics.mean(row["full_evidence"] for row in positives) if positives else None,
        "evidence_coverage": statistics.mean(row["evidence_coverage"] for row in positives) if positives else None,
        "evidence_hit_rate": statistics.mean(row["evidence_hit"] for row in positives) if positives else None,
        "answerable_empty_count": sum(not row["hits"] for row in positives),
        "answerable_empty_rate": statistics.mean(not row["hits"] for row in positives) if positives else None,
        "unanswerable_nonempty_count": sum(bool(row["hits"]) for row in negatives),
        "unanswerable_nonempty_rate": statistics.mean(bool(row["hits"]) for row in negatives) if negatives else None,
        "mean_context_characters": statistics.mean(row["context_characters"] for row in rows),
        "mean_retained_chunks": statistics.mean(len(row["hits"]) for row in rows),
    }


def evaluate(cases, cached_hits, texts, clauses, k, threshold):
    rows = []
    for case in cases:
        hits = filter_hits(cached_hits[case["id"]], k, threshold)
        rows.append({
            "case_id": case["id"], "query": case["query"], "group": case["evaluation_group"],
            "k": k, "threshold": threshold, "hits": hits,
            **score_hits(case, hits, texts, clauses),
        })
    return rows


def load_inputs(cache):
    config = read_json(cache / "config.json")
    dataset = read_json(cache / "old_dataset_snapshot.json")
    validation = read_json(cache / "validation_snapshot.json")
    frozen_texts = read_json(cache / "documents_snapshot.json")
    if any(item is None for item in (config, dataset, validation, frozen_texts)):
        raise ValueError("Missing frozen inputs; this command never downloads or regenerates data")
    if (digest(dataset) != config["old_dataset_sha256"]
            or digest(validation) != config["validation_sha256"]
            or digest(frozen_texts) != config["documents_sha256"]):
        raise ValueError("Frozen input hashes do not match")
    current_dataset, texts, clauses = load_dataset()
    if digest(texts) != config["documents_sha256"] or digest(current_dataset) != digest(dataset):
        raise ValueError("Current policy or gold dataset changed; cached scores cannot validate it")
    current_validation = read_json(HERE / "chunk_validation.json")
    if digest(current_validation) != digest(validation):
        raise ValueError("Validation labels changed since caching")
    sources = {
        "old60": (dataset, read_json(cache / "development_results.json")),
        "seen20": (validation, read_json(cache / "validation_results.json")),
    }
    cases, cached_hits, ids = [], {}, set()
    for group, (questions, records) in sources.items():
        if records is None:
            raise ValueError("Missing retrieval records; this command does not call a retriever")
        for original in questions["cases"]:
            case = {**original, "evaluation_group": group}
            if case["id"] in ids or any(key not in clauses for key in case["requires"]):
                raise ValueError("Duplicate case or unknown gold evidence")
            ids.add(case["id"])
            row = records.get(f"{case['id']}:500/80/k8")
            if row is None or row["case_id"] != case["id"] or len(row["hits"]) != max(KS):
                raise ValueError("Every question needs all eight frozen baseline hits")
            hits = row["hits"]
            filter_hits(hits, max(KS), None)
            if any(left["score"] < right["score"] for left, right in zip(hits, hits[1:])):
                raise ValueError("Cached scores must be sorted from highest to lowest")
            rescored = score_hits(case, hits, texts, clauses)
            if any(rescored[key] != row[key] for key in ("full_evidence", "evidence_coverage", "clause_hits")):
                raise ValueError("Cached evidence annotations are stale")
            cases.append(case)
            cached_hits[case["id"]] = hits
    manifest = {
        "documents_sha256": digest(texts), "dataset_sha256": digest(dataset),
        "seen_validation_sha256": digest(validation), "baseline_hits_sha256": digest(cached_hits),
        "cutting": {"chunk_size": 500, "overlap": 80}, "embedding": config["embedding_model"],
        "metric": "COSINE", "engine": config["engine"],
        "k_values": list(KS), "thresholds": list(THRESHOLDS),
        "selection": "exploratory comparison only; no independent holdout or automatic production change",
        "api_requests": {"embedding": 0, "deepseek": 0}, "database_access": False,
    }
    return cases, cached_hits, texts, clauses, manifest


def top1_diagnostics(cases, cached_hits):
    by_label = {True: [], False: []}
    for case in cases:
        by_label[bool(case["requires"])].append(cached_hits[case["id"]][0]["score"])
    positives, negatives = by_label[True], by_label[False]
    if not positives or not negatives:
        raise ValueError("Diagnostics require both answerable and unanswerable cases")
    return {
        "positive_min": min(positives), "positive_max": max(positives),
        "negative_min": min(negatives), "negative_max": max(negatives),
        "can_keep_all_positives_and_reject_all_negatives": max(negatives) < min(positives),
        "negative_cases": [{
            "id": case["id"], "query": case["query"],
            "top1_score": cached_hits[case["id"]][0]["score"],
            "top1_source": cached_hits[case["id"]][0]["source"],
        } for case in cases if not case["requires"]],
    }


def lost_evidence(cases, baseline_rows, filtered_rows):
    baseline = {row["case_id"]: row for row in baseline_rows}
    filtered = {row["case_id"]: row for row in filtered_rows}
    losses = []
    for case in cases:
        before, after = baseline[case["id"]], filtered[case["id"]]
        lost = [key for key, found in before["clause_hits"].items()
                if found and not after["clause_hits"][key]]
        if lost:
            losses.append({"case_id": case["id"], "query": case["query"], "lost_clauses": lost,
                           "no_results": not after["hits"]})
    return losses


def percentage(value):
    return "N/A" if value is None else f"{value * 100:.1f}%"


def make_report(summaries, diagnostics, losses, candidate_losses):
    lines = [
        "# 相关性阈值与 Top K 联合比较", "", "## 范围与边界", "",
        "固定当前500/80切分及text-embedding-v3，复用上一轮NumPy精确余弦排序的Top8分数。",
        "先截取Top K，再按score >= threshold过滤，与目前生产检索的过滤顺序一致。",
        "比较K=1、3、5、8与不设阈值及0.30至0.80、步长0.05的阈值，共48组。",
        "共80题：原60题与上一轮新增20题。二者都已被查看，因此本轮全部是探索数据，不是新的独立留出验证。",
        "共66道库内题、14道库外题；题目由助手构造并标注，来自10篇短模拟政策，等价依据标注可能不完整。",
        "不调用Embedding或DeepSeek，不连接数据库，不修改生产参数，没有测最终回答、Token费用或线上延迟。", "",
        "## 指标定义", "",
        "- 完整证据：问题所需全部标注条款都被返回文本覆盖；条款覆盖率是每题覆盖比例的宏平均。",
        "- 库内空结果：可回答问题被过滤至空。是误拒答风险代理，不等于完整业务工作流的实际拒答率。",
        "- 库外有结果：无答案问题仍有片段进入上下文。是误放行代理，不等于生成幻觉率。",
        "- 返回字符：全部80题平均值，包括空结果；不是实际Token数或账单费用。", "",
        "## 全量比较", "",
        "| K | 阈值 | 完整证据/66 | 条款覆盖率 | 库内空结果/66 | 库外有结果/14 | 平均返回字符 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for k in KS:
        for threshold in THRESHOLDS:
            row = summaries[setting_key(k, threshold)]["all"]
            label = "不过滤" if threshold is None else f"{threshold:.2f}"
            lines.append(f"| {k} | {label} | {row['full_evidence_count']}/66 | {percentage(row['evidence_coverage'])} | {row['answerable_empty_count']}/66 | {row['unanswerable_nonempty_count']}/14 | {row['mean_context_characters']:.1f} |")
    lines += ["", "## 已观察的新20题单独核对", "",
              "这一分组已在上一轮使用过，只用于诊断，不在本轮重新称为留出集。", "",
              "| K | 阈值 | 完整证据/16 | 条款覆盖率 | 库内空结果/16 | 库外有结果/4 |",
              "|---:|---:|---:|---:|---:|---:|"]
    for k in (3, 5):
        for threshold in THRESHOLDS:
            row = summaries[setting_key(k, threshold)]["seen20"]
            label = "不过滤" if threshold is None else f"{threshold:.2f}"
            lines.append(f"| {k} | {label} | {row['full_evidence_count']}/16 | {percentage(row['evidence_coverage'])} | {row['answerable_empty_count']}/16 | {row['unanswerable_nonempty_count']}/4 |")
    lines += ["", "## 分数能否分开库内与库外", "",
              f"库内题Top1分数范围：{diagnostics['positive_min']:.4f} 至 {diagnostics['positive_max']:.4f}。",
              f"库外题Top1分数范围：{diagnostics['negative_min']:.4f} 至 {diagnostics['negative_max']:.4f}。"]
    if not diagnostics["can_keep_all_positives_and_reject_all_negatives"]:
        lines.append("最高库外分数不低于最低库内分数，因此单一全局阈值无法同时保留全部库内问题的片段、拒绝全部库外问题。这不代表所有片段都已得到语义相关性标注。")
    lines += ["", "| 库外题 | 问题 | Top1分数 | 最相近来源 |", "|---|---|---:|---|"]
    for row in diagnostics["negative_cases"]:
        lines.append(f"| {row['id']} | {row['query']} | {row['top1_score']:.4f} | {row['top1_source']} |")
    lines += ["", "## 与当前默认值的直接比较", ""]
    for k in (3, 5):
        raw = summaries[setting_key(k, None)]["all"]
        filtered = summaries[setting_key(k, 0.45)]["all"]
        lines.append(f"K={k}时，0.45将完整证据题数从{raw['full_evidence_count']}改为{filtered['full_evidence_count']}/66；库外有结果从{raw['unanswerable_nonempty_count']}改为{filtered['unanswerable_nonempty_count']}/14；库内空结果为{filtered['answerable_empty_count']}/66。")
        lines.append(f"K={k}时，0.45造成已召回条款丢失的题数为{len(losses[str(k)])}，明细见results中的lost_evidence_at_045.json。")
    conservative = summaries[setting_key(5, 0.55)]["all"]
    stricter = summaries[setting_key(5, 0.60)]["all"]
    wider = summaries[setting_key(8, 0.55)]["all"]
    lines += ["", "## 下一轮可以验证的候选", "",
              f"- 保留覆盖优先：K=5、阈值0.55，完整证据{conservative['full_evidence_count']}/66，库内空结果{conservative['answerable_empty_count']}/66，库外仍有结果{conservative['unanswerable_nonempty_count']}/14，平均返回{conservative['mean_context_characters']:.1f}字符。",
              f"- 库外过滤优先：K=5、阈值0.60，完整证据{stricter['full_evidence_count']}/66，库内空结果{stricter['answerable_empty_count']}/66，库外仍有结果{stricter['unanswerable_nonempty_count']}/14，平均返回{stricter['mean_context_characters']:.1f}字符。",
              f"- 更多上下文：K=8、阈值0.55，完整证据{wider['full_evidence_count']}/66，平均返回{wider['mean_context_characters']:.1f}字符；本轮没有验证最终生成是否值得这些额外内容。",
              "这些候选来自已观察数据，不是独立验证通过的推荐配置。业务是否接受漏证据或库外有片段，仍需明确。", "",
              "## 0.60过滤造成的具体证据损失", ""]
    for loss in candidate_losses:
        lines.append(f"- {loss['case_id']}：{loss['query']}；K=5时丢失标注条款{', '.join(loss['lost_clauses'])}，过滤后{'完全为空' if loss['no_results'] else '仍有其他片段'}。")
    lines += ["", "## 怎样作出决策", "",
              "没有预设或替用户决定可接受的误放行、误拒答上限，因此不自动选一个所谓最佳阈值。",
              "先确定业务容忍度，再在开发数据上选满足覆盖和误拒答要求的候选，用新的真实问题或独立标注确认；不能继续在这些已观察题上调参并宣称泛化。",
              "同一非空排名列表先取K再过滤时，是否为空只取决于Top1分数。因此提高K不会解决全局阈值的库外有结果问题，但可能补充政策条款并增加上下文。",
              "相似度只是向量接近程度，部分库外题可能和相关领域高度相似。有片段不代表片段足以回答，也不代表模型一定生成错误答案。",
              "若全局分数区分能力不足，可比较候选召回加重排或问题可回答性判断，仍需独立评测，不能仅换一个阈值就承诺解决。", "",
              "## 复现", "", "```powershell",
              "python -X utf8 -m evaluation.threshold_k",
              "python -X utf8 -m unittest evaluation.test_threshold_k -v", "```", "",
              "运行只读取本地缓存和知识库文本，缺失或快照不匹配时直接停止，不会补发API请求。",
              "本地结果目录：evaluation/results/threshold_k_20261010。生产配置未改动。"]
    path = HERE / "threshold_k_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run(cache, output):
    cases, cached_hits, texts, clauses, manifest = load_inputs(cache)
    previous = read_json(output / "config.json")
    if previous is not None and previous != manifest:
        raise ValueError("Inputs changed; use a new output directory")
    records, summaries = {}, {}
    for k in KS:
        for threshold in THRESHOLDS:
            key = setting_key(k, threshold)
            rows = evaluate(cases, cached_hits, texts, clauses, k, threshold)
            records[key] = rows
            summaries[key] = {
                group: aggregate([row for row in rows if group == "all" or row["group"] == group])
                for group in GROUPS
            }
    diagnostics = top1_diagnostics(cases, cached_hits)
    losses = {str(k): lost_evidence(cases, records[setting_key(k, None)],
                                   records[setting_key(k, 0.45)]) for k in (3, 5)}
    candidate_losses = lost_evidence(cases, records[setting_key(5, None)], records[setting_key(5, 0.60)])
    write_json(output / "config.json", manifest)
    write_json(output / "question_snapshot.json", cases)
    write_json(output / "retrieval.json", records)
    write_json(output / "summary.json", summaries)
    write_json(output / "score_diagnostics.json", diagnostics)
    write_json(output / "lost_evidence_at_045.json", losses)
    write_json(output / "lost_evidence_at_060_k5.json", candidate_losses)
    report = make_report(summaries, diagnostics, losses, candidate_losses)
    print({"questions": len(cases), "settings": len(summaries), "api_requests": manifest["api_requests"]})
    for k in (3, 5):
        for threshold in (None, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70):
            key = setting_key(k, threshold)
            print(key, summaries[key]["all"])
    print(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    run(args.cache, args.output)


if __name__ == "__main__":
    main()
