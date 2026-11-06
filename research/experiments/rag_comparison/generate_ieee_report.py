"""Create evidence-gated IEEE results prose, LaTeX tables and figures."""
import json
import argparse
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def write_new(path: Path, content: str) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite research output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as f:
        f.write(content)


def write_artifact(path: Path, content: str | bytes, refresh: bool = False) -> None:
    payload = content.encode("utf-8") if isinstance(content, str) else content
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not refresh:
            raise FileExistsError(f"Refusing to overwrite research output: {path}")
        backup = path.with_name(path.stem + ".pre_refresh" + path.suffix)
        if backup.exists():
            raise FileExistsError(f"Refusing to overwrite prior-version backup: {backup}")
        with backup.open("xb") as f:
            f.write(path.read_bytes())
        path.write_bytes(payload)
    else:
        with path.open("xb") as f:
            f.write(payload)


def generate(root: Path = ROOT, refresh: bool = False) -> list[Path]:
    config = json.loads((root / "system_configuration.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "experiment_manifest.json").read_text(encoding="utf-8"))
    corpus = json.loads((root / "frozen_corpus_report.json").read_text(encoding="utf-8"))
    if manifest.get("corpus_sha256") != "d9c6dd16c44bf402f26e922449c988a4e19d8bf4edd285addb1999d6f8f06bb8" or corpus.get("corpus_sha256") != manifest["corpus_sha256"]:
        raise ValueError("Frozen corpus identity mismatch")
    docs = corpus.get("documents", [])
    chunks = sum(int(d.get("chunks", 0)) for d in docs)
    chapters = ", ".join(str(d.get("chapter_number")) for d in docs)
    qs = [json.loads(x) for x in (root / "datasets" / "questions.jsonl").read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    split_counts = {s: sum(q.get("split") == s for q in qs) for s in ("dev", "test")}
    qdist = {}; 
    for q in qs: qdist[q["chapter_number"]] = qdist.get(q["chapter_number"], 0) + 1
    qdistribution = ", ".join(f"{ch}: {count}" for ch, count in sorted(qdist.items()))
    settings = config.get("settings", {})
    embedding = settings.get("embedding_model", {}).get("value", "not captured")
    embedding_digest = settings.get("embedding_digest", {}).get("value", "not captured")
    generation = settings.get("generation_model", {}).get("value", "not captured")
    generation_digest = settings.get("generation_digest", {}).get("value", "not captured")
    rmetrics = root / "results" / "retrieval_metrics.json"
    gmetrics = root / "results" / "generation_comparison.json"
    retrieval_text = "No judged relevance metrics are reportable until the two-reviewer qrels have been adjudicated. Raw retrieval rankings are execution traces only."
    generation_text = "LearnMateAI RAG answers and two-reviewer answer-quality judgments are unavailable; no human-scored answer comparison is claimed."
    baseline_path = root / "generation" / "no_retrieval.json"
    baseline_summary = ""
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        ok = [x for x in baseline.get("records", []) if x.get("status") == "success"]
        latencies = sorted(float(x["latency_seconds"]) for x in ok)
        p95 = latencies[int((len(latencies)-1)*.95)] + (latencies[min(int((len(latencies)-1)*.95)+1, len(latencies)-1)] - latencies[int((len(latencies)-1)*.95)]) * (((len(latencies)-1)*.95) % 1) if latencies else None
        baseline_summary = f"Retrieval-free technical generation completed for {len(ok)}/{len(baseline.get('records', []))} development questions (IDs: {', '.join(baseline.get('selected_question_ids', []))}). Mean response latency: {sum(latencies)/len(latencies):.3f} s; median: {sorted(latencies)[(len(latencies)-1)//2] if len(latencies)%2 else (sorted(latencies)[len(latencies)//2-1]+sorted(latencies)[len(latencies)//2])/2:.3f} s; p95 (linear interpolation): {p95:.3f} s. These are operational measurements, not answer-quality metrics."
    elif all((root / "runs" / f"{m}.json").is_file() for m in ("dense", "fts", "hybrid")):
        retrieval_text = "Dense, PostgreSQL FTS, and hybrid trace files exist. Validate their frozen provenance with `python eval_retrieval.py --validate-only`. Relevance metrics are withheld until reviewed qrels are adjudicated; raw run completion alone is not effectiveness evidence."
    if rmetrics.exists():
        data = json.loads(rmetrics.read_text(encoding="utf-8")); lines = []
        for mode, result in data["modes"].items():
            m = result["metrics"]; l = result["latency_ms"]
            lines.append(f"{mode}: P@5={m['precision_at_5']['mean']}, R@5={m['recall_at_5']['mean']}, MRR@10={m['mrr_at_10']['mean']}, nDCG@10={m['ndcg_at_10']['mean']}; latency median/p95={l['median']}/{l['p95']} ms (n={m['precision_at_5']['n']}).")
        retrieval_text = "\n".join(lines)
    if gmetrics.exists():
        data = json.loads(gmetrics.read_text(encoding="utf-8")); lines = []
        for cond in ("no_retrieval", "rag"):
            lines.append(f"{cond}: " + ", ".join(f"{m}={data[cond][m]['mean']} (n={data[cond][m]['n']})" for m in ("correctness", "faithfulness", "explanation_quality", "citation_support")))
        generation_text = "\n".join(lines)
    body = f"""# IEEE Research Results — LearnMateAI RAG Comparison

## A. Dataset and experimental setup

The evaluation scope is limited to nine NCERT Class 10 Science chapters ({chapters}); it is not a complete 13-chapter evaluation. Chapters 4, 5, 6, and 8 were excluded due to unresolved ingestion failures. The frozen snapshot is `nine_science_03` with SHA-256 `{manifest['corpus_sha256']}` and {chunks} indexed passages. The selected question set contains {len(qs)} candidate questions ({split_counts['dev']} development, {split_counts['test']} selected held-out); the original 32-question test set remains authoritative. Per-chapter distribution: {qdistribution}.

The frozen configuration identifies BGE-M3 `{embedding}` (digest `{embedding_digest}`) and Llama 3 8B `{generation}` (digest `{generation_digest}`). See `system_configuration.json` for implementation paths and the distinction between frozen runtime evidence and source defaults. Retrieval conditions are dense vector similarity, PostgreSQL FTS (not BM25), and reciprocal-rank-fusion (RRF) hybrid retrieval. No settings were tuned on held-out outcomes.

Human relevance judgments and answer-quality scores are reportable only after independent review and explicit adjudication. Candidate passages and generated answers are not ground truth.

## B. Retrieval findings

{retrieval_text}

## C. RAG versus retrieval-free generation

{baseline_summary}\n\n{generation_text}

## D. Technical interpretation and limitations

No comparative effectiveness conclusion is supported by the currently available artifacts. The frozen corpus covers nine chapters selected after four chapter-ingestion failures; this limited coverage and failure-driven chapter selection may create selection bias and limits generalization to the full curriculum. Question labels are currently unverified. This report does not claim that LearnMateAI outperforms commercial assistants.
"""
    report_path = root / "results" / "ieee_research_results.md"
    write_artifact(report_path, body, refresh)
    outputs = [report_path]
    if rmetrics.exists():
        data = json.loads(rmetrics.read_text(encoding="utf-8"))
        tex = [r"\begin{table*}[t]", r"\centering", r"\caption{Retrieval effectiveness on the frozen nine-chapter corpus.}", r"\label{tab:retrieval}", r"\begin{tabular}{lrrrrrr}", r"\hline", r"Method & P@5 & R@5 & MRR@10 & nDCG@10 & Median (ms) & P95 (ms) \\", r"\hline"]
        for mode, label in (("dense", "Dense"), ("fts", "PostgreSQL FTS"), ("hybrid", "Hybrid")):
            d = data["modes"][mode]; v = d["metrics"]; l = d["latency_ms"]
            f = lambda x: "--" if x is None else f"{x:.3f}"
            tex.append(f"{label} & {f(v['precision_at_5']['mean'])} & {f(v['recall_at_5']['mean'])} & {f(v['mrr_at_10']['mean'])} & {f(v['ndcg_at_10']['mean'])} & {f(l['median'])} & {f(l['p95'])} \\")
        tex.extend([r"\hline", r"\end{tabular}", r"\end{table*}"])
        p = root / "results" / "ieee_retrieval_table.tex"; write_artifact(p, "\n".join(tex) + "\n", refresh); outputs.append(p)
        try:
            import matplotlib.pyplot as plt
        except ImportError as exc:
            raise RuntimeError("Install matplotlib in the research environment to render real-data figures") from exc
        labels = ["Dense", "PostgreSQL FTS", "Hybrid"]
        vals = [data["modes"][m]["metrics"]["ndcg_at_10"]["mean"] for m in ("dense", "fts", "hybrid")]
        fig, ax = plt.subplots(figsize=(7.0, 3.0)); ax.bar(labels, vals); ax.set_ylabel("nDCG@10"); ax.set_ylim(0, 1); ax.set_title("Retrieval effectiveness (nDCG@10)"); fig.tight_layout()
        buffer = BytesIO(); fig.savefig(buffer, format="png", dpi=300); plt.close(fig)
        p = root / "results" / "retrieval_metrics.png"; write_artifact(p, buffer.getvalue(), refresh); outputs.append(p)
        latency = [data["modes"][m]["latency_ms"]["median"] for m in ("dense", "fts", "hybrid")]
        fig, ax = plt.subplots(figsize=(7.0, 3.0)); ax.bar(labels, latency); ax.set_ylabel("Median retrieval latency (ms)"); ax.set_title("Retrieval latency by method"); fig.tight_layout()
        buffer = BytesIO(); fig.savefig(buffer, format="png", dpi=300); plt.close(fig)
        p = root / "results" / "retrieval_latency.png"; write_artifact(p, buffer.getvalue(), refresh); outputs.append(p)
    if gmetrics.exists():
        data = json.loads(gmetrics.read_text(encoding="utf-8"))
        tex = [r"\begin{table*}[t]", r"\centering", r"\caption{Human-rated generation quality. Citation support is interpreted separately for the retrieval-free condition.}", r"\label{tab:generation}", r"\begin{tabular}{lrrrr}", r"\hline", r"Condition & Correctness & Faithfulness & Explanation quality & Citation support \\", r"\hline"]
        for cond, label in (("no_retrieval", "Retrieval-free Llama 3 8B"), ("rag", "LearnMateAI RAG")):
            vals = [data[cond][m]["mean"] for m in ("correctness", "faithfulness", "explanation_quality", "citation_support")]
            tex.append(label + " & " + " & ".join(f"{x:.3f}" for x in vals) + r" \\")
        tex.extend([r"\hline", r"\end{tabular}", r"\end{table*}"])
        p = root / "results" / "ieee_generation_table.tex"; write_artifact(p, "\n".join(tex) + "\n", refresh); outputs.append(p)
        import matplotlib.pyplot as plt
        names = ["Correctness", "Faithfulness", "Explanation", "Citation support"]
        fig, ax = plt.subplots(figsize=(7.0, 3.0)); width = .36; x = range(len(names))
        for offset, cond, label in ((-.18, "no_retrieval", "No retrieval"), (.18, "rag", "LearnMateAI RAG")):
            ax.bar([i + offset for i in x], [data[cond][m]["mean"] for m in ("correctness", "faithfulness", "explanation_quality", "citation_support")], width, label=label)
        ax.set_xticks(list(x), names); ax.set_ylim(0, 2); ax.set_ylabel("Mean reviewer score (0–2)"); ax.legend(); fig.tight_layout()
        buffer = BytesIO(); fig.savefig(buffer, format="png", dpi=300); plt.close(fig)
        p = root / "results" / "generation_comparison.png"; write_artifact(p, buffer.getvalue(), refresh); outputs.append(p)
    return outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Preserve each previous output as .pre_refresh before replacing it")
    args = parser.parse_args()
    for item in generate(refresh=args.refresh): print(item)
