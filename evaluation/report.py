"""Build an offline report from completed retrievals and reviewed answers."""

import argparse
from pathlib import Path
import statistics

from evaluation.top_k import DEFAULT_OUTPUT, digest, read_json, write_json


HERE = Path(__file__).resolve().parent


def rate(value):
    return f"{value * 100:.1f}%"


def validate_reviews(answers, reviews):
    if not answers or set(answers) != set(reviews["reviews"]):
        raise ValueError("Every answer needs exactly one review")
    if digest(answers) != reviews.get("answers_sha256"):
        raise ValueError("Answers changed; old review scores must not be reused")


def report(output=DEFAULT_OUTPUT):
    dataset = read_json(output / "dataset_snapshot.json")
    texts = read_json(output / "documents_snapshot.json")
    config = read_json(output / "config.json")
    if not config or not dataset or digest(dataset) != config["dataset_sha256"] or digest(texts) != config["documents_sha256"]:
        raise ValueError("Frozen dataset/source hashes differ")
    retrieval = read_json(output / "retrieval_summary.json")
    answers = read_json(output / "answers.json")
    reviews = read_json(HERE / "answer_reviews.json")
    selection = read_json(output / "selection.json")
    budget = read_json(output / "request_budget.json")
    validate_reviews(answers, reviews)
    if reviews.get("dataset_sha256") != config["dataset_sha256"]:
        raise ValueError("Reviews belong to a different dataset")
    if any(answer["error"] or answer["final_action"] != "auto_reply" or not answer["usage"] for answer in answers.values()):
        raise ValueError("Do not report fallback or missing-usage responses as successful generations")
    settings = read_json(output / "generation_settings.json")
    generation = {}
    for split in ("dev", "test", "all"):
        generation[split] = {}
        for k in settings["k_values"]:
            pairs = [(key, value) for key, value in answers.items()
                     if value["k"] == k and (split == "all" or value["split"] == split)]
            subset_reviews = [reviews["reviews"][key] for key, _ in pairs]
            generation[split][str(k)] = {
                "answers": len(pairs),
                "core_question_correct": sum(review["core_question_correct"] for review in subset_reviews),
                "rubric_complete": sum(review["rubric_complete"] for review in subset_reviews),
                "responses_with_unsupported_claims": sum(bool(review["unsupported_claims"]) for review in subset_reviews),
                "abstained": sum(review.get("abstained", False) for review in subset_reviews),
                "unanswerable_questions": sum("abstained" in review for review in subset_reviews),
                "mean_input_tokens": statistics.mean(value["usage"]["input_tokens"] for _, value in pairs),
                "mean_output_tokens": statistics.mean(value["usage"]["output_tokens"] for _, value in pairs),
                "total_tokens": sum(value["usage"]["total_tokens"] for _, value in pairs),
                "cache_read_tokens": sum(value["usage"].get("input_token_details", {}).get("cache_read", 0) for _, value in pairs),
                "median_generation_ms": statistics.median(value["generation_ms"] for _, value in pairs),
            }
    audit = {
        "request_budget": budget,
        "total_deepseek_tokens": sum(value["usage"]["total_tokens"] for value in answers.values()),
        "dataset_sha256": config["dataset_sha256"],
        "documents_sha256": config["documents_sha256"],
        "answers_sha256": digest(answers),
        "reviews_sha256": digest(reviews),
    }
    write_json(output / "final_summary.json", {"retrieval": retrieval, "generation": generation, "audit": audit})
    baseline = generation["all"]["3"]
    candidate = generation["all"][str(selection["candidate_k"])]
    increase = candidate["mean_input_tokens"] / baseline["mean_input_tokens"] - 1
    lines = [
        "# Top K 小样本评测报告", "",
        "## 结论", "",
        "本次没有证明 Top 3 是最优，也没有证据支持将线上默认值直接改成 Top 5。保留当前默认值作为基线。",
        "开发集上 Top 5 补齐了部分标注证据，留出集上 Top 3 与 Top 5 完整证据覆盖均为 14/16。",
        f"20 道生成子集上，Top 5 平均输入 Token 比 Top 3 增加 {rate(increase)}，没有显示留出回答样本的明确改善。",
        "Top 8 在这个留出检索集上补齐了全部标注证据，但没有测试它的生成效果；不能据此宣布 Top 8 通用最优。", "",
        "## 范围与冻结条件", "",
        "- 10 篇演示文档，4,843 字符，当前 Milvus 14 条；评测前逐条比较 source 和 text，确认与本地切分一致。",
        "- 60 道助手根据原文构造并标注的题：开发集 40（34 可回答、6 库外），留出集 20（16 可回答、4 库外）。",
        "- 按问题场景分组；不同集合仍可能共享原始政策条款。不是文档隔离测试，也不是独立真实用户流量。",
        "- 金标准为原始条款及其文本范围。标注包含部分等价来源，但不保证覆盖所有等价依据。",
        "- 复用现有 500/80 递归字符切分、text-embedding-v3、COSINE 检索，无重排、无相关性阈值。",
        "- 候选 K 只根据开发集挑选：完整证据率优先，其次覆盖率，再考虑上下文长度。选择结果在生成前保存。",
        "- 20 道预先指定生成题（开发 10、留出 10），只比较基线 K=3 和开发集选出的 K=5，共 40 份回答。",
        "- 复用现有 knowledge_only_context_node 和 generate_reply_node 的 Prompt，不走完整 /chat，不执行 finish，不写业务数据库。",
        "- 为降低采样噪音和限制费用，评测固定 temperature=0、输出上限900 Token、超时45秒、重试0；线上默认参数未改变。",
        "- 每题每 K 只生成一次，没有重复性、并发或长期线上测试。40 份均正常结束，无输出截断。", "",
        "## 检索结果", "",
        "证据命中率：至少一个预先标注条款被召回。完整证据率：全部标注条款的文本范围被返回片段覆盖。",
        "覆盖率为每题已覆盖条款比例的宏平均；库外题不进入这些指标的分母。",
        "这些是保守的标注文本跨度指标，不等于语义召回率，也不能直接当作回答准确率。", "",
        "| 集合 | K | 证据命中率 | 条款覆盖率 | 全证据题数 | 平均返回字符（含库外题） |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for split, label in (("dev", "开发"), ("test", "留出")):
        for k in (1, 3, 5, 8):
            row = retrieval[split][str(k)]
            full_count = round(row["full_evidence"] * row["answerable_questions"])
            lines.append(f"| {label} | {k} | {rate(row['evidence_hit'])} | {rate(row['evidence_coverage'])} | {full_count}/{row['answerable_questions']} | {row['mean_context_characters']:.1f} |")
    lines += [
        "", "source_precision_proxy 仅按来源文件判断，不能当成真实片段相关性或噪音率。原始记录中保留该诊断指标，但不据此宣称精准率。",
        "10 道库外题在四个 K 下均返回了片段，说明当前 Top K 排序没有提供相关性拒绝机制。", "",
        "## 回答与 Token", "",
        "回答由本次助手逐条对照原文核对，非独立人工盲评。核心政策方向正确不代表整篇完全有据。",
        "标注要点齐全率可能要求问题之外的补充要点，不能把不通过直接理解为用户问题答错。", "",
        "| 集合 | K | 核心方向通过 | 标注要点齐全 | 含无依据陈述或界面建议 | 库外正确拒答 | 平均输入Token | 平均输出Token |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for split, label in (("dev", "开发生成子集"), ("test", "留出生成子集"), ("all", "合计")):
        for k in settings["k_values"]:
            row = generation[split][str(k)]
            lines.append(f"| {label} | {k} | {row['core_question_correct']}/{row['answers']} | {row['rubric_complete']}/{row['answers']} | {row['responses_with_unsupported_claims']}/{row['answers']} | {row['abstained']}/{row['unanswerable_questions']} | {row['mean_input_tokens']:.1f} | {row['mean_output_tokens']:.1f} |")
    lines += [
        "", "留出生成子集仅含8道可回答题和2道库外题，并未包含所有检索失败题。不能外推为整套题或线上100%准确。",
        "Token来自接口实际 usage_metadata。提供商缓存命中不同，因此输入Token涨幅不等于人民币费用涨幅。未查询账单或推算金额。", "",
        "## 可复查案例", "",
        "- D31：跨无理由、运输破损和退款到账。K=3 未返回专项运费及退款到账完整条款；回答仍回应了两个直接问题，但没有1至5工作日补充信息，部分运费表述缺少直接检索依据。K=5 返回了依据并补充这些要点。",
        "- T08：库存、检测结论、退款金额能否承诺。K=3/5 未返回标注的质量处理条款，K=8 才覆盖。其他政策可能提供部分等价依据，应人工检查而不是简单宣布完全未召回。",
        "- T15：故障处理选择、维修不退款、已收货仅退款。K=3/5 漏掉标注的质量处理条款，K=8 补齐。本题未在生成子集中，尚未验证最终答案。",
        "- D35：会员费用未知，两个 K 都没有编造价格，但生成了未确认存在的会员中心页面；K=5 还给出具体App导航。应限制无依据产品界面建议。",
        "- T17：未知优惠券叠加规则，两个 K 都正确拒绝给出规则，但都建议查看未确认的结算页功能。",
        "- T20：积分规则未知时建议提供订单号；没有编造兑换比例，但政策咨询的订单引导不必要。",
        "- 发票回复中的查询实际开票状态承诺需要与真实 Tool 能力单独核对，本次纯 RAG 评测没有验证这种业务能力。", "",
        "## 耗时与预算", "",
        f"- Embedding 请求计数：{budget['embedding']}；DeepSeek请求计数：{budget['deepseek']}，未超出80/40授权上限。",
        f"- DeepSeek累计输入输出Token：{audit['total_deepseek_tokens']:,}。",
        f"- K=3生成中位耗时：{baseline['median_generation_ms'] / 1000:.3f}秒；K=5：{candidate['median_generation_ms'] / 1000:.3f}秒。",
        "- Milvus检索中位耗时约3至4毫秒，已预热并轮换K顺序；不含Embedding、网络环境波动和生成过程，不代表并发性能。", "",
        "## 后续建议", "",
        "保持线上参数不变。先对失败题补齐等价证据标注、增加真实问题和更长文档，再考虑候选多召回加重排或按政策过滤。",
        "若比较K=8的回答或重复生成，需要新一轮费用授权；当前批准的40次DeepSeek调用已用完。",
        "不要为提高分数在这次留出集上反复调参，修订标注后应建立新版本及新的独立留出题。", "",
        "## 复现与审计", "",
        "题集：top_k_dataset.json；评审：answer_reviews.json；命令见本目录README。",
        "本地原始输出位于results/top_k_20261009，包含查询向量、检索结果、完整回答、usage、快照和预算。results默认不提交Git。",
        "再次运行相同目录会复用缓存；复用结果是审计，不是独立重测。独立重测必须使用新目录并取得新费用授权。", "",
        f"- dataset_sha256: `{audit['dataset_sha256']}`",
        f"- documents_sha256: `{audit['documents_sha256']}`",
        f"- answers_sha256: `{audit['answers_sha256']}`",
        f"- reviews_sha256: `{audit['reviews_sha256']}`",
    ]
    path = HERE / "top_k_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    report(parser.parse_args().output)


if __name__ == "__main__":
    main()
