"""
inspect.py — Structural inspection of CUAD_v1.json and companion files.

Purpose:
    Ground the ingestion design in the actual dataset structure rather than
    assumptions about SQuAD 2.0. Prints a comprehensive diagnostic covering:

      1. File presence
      2. Top-level JSON structure
      3. QA inventory (counts, categories, ID uniqueness)
      4. Answer span integrity (offsets, <omitted>, redactions)
      5. Paragraphs per contract
      6. A worked sample of one contract
      7. JSON <-> TXT cross-check
      8. master_clauses.csv column inspection

Run:
    python -m src.ingest.inspect
    (or: python src/ingest/inspect.py)
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RAW = Path("data/raw/CUAD_v1")
JSON_PATH = RAW / "CUAD_v1.json"
TXT_DIR = RAW / "full_contract_txt"
CSV_PATH = RAW / "master_clauses.csv"

REDACTION_MARKERS = ("***", "___", "[*", "*]", "[ ]")
OMITTED_TOKEN = "<omitted>"


# ---------------------------------------------------------------------------
# Pretty-printing helpers
# ---------------------------------------------------------------------------

def section(n: int, title: str) -> None:
    print()
    print("=" * 72)
    print(f"{n}. {title}")
    print("=" * 72)


def sub(title: str) -> None:
    print()
    print(f"--- {title} ---")


# ---------------------------------------------------------------------------
# 1. File presence
# ---------------------------------------------------------------------------

def check_files() -> bool:
    section(1, "FILE PRESENCE")
    ok = True
    for p in (JSON_PATH, TXT_DIR, CSV_PATH):
        exists = p.exists()
        flag = "OK     " if exists else "MISSING"
        print(f"  [{flag}]  {p}")
        if not exists:
            ok = False
    return ok


# ---------------------------------------------------------------------------
# 2. Top-level structure
# ---------------------------------------------------------------------------

def load_json() -> dict:
    print(f"\n  Loading {JSON_PATH} ...")
    with JSON_PATH.open(encoding="utf-8") as f:
        payload = json.load(f)
    print(f"  Loaded. Top-level keys: {list(payload.keys())}")
    return payload


def inspect_top_level(payload: dict) -> list[dict]:
    section(2, "TOP-LEVEL STRUCTURE")

    print(f"  version field: {payload.get('version', '<not present>')}")

    data = payload.get("data", [])
    print(f"  data[] length: {len(data)}")
    if not data:
        print("  No contracts found in data[]. Aborting.")
        sys.exit(1)

    first = data[0]
    print(f"  data[0] keys: {list(first.keys())}")
    print(f"  data[0].title: {first.get('title', '<missing>')!r}")

    paras = first.get("paragraphs", [])
    print(f"  data[0].paragraphs length: {len(paras)}")

    if paras:
        print(f"  data[0].paragraphs[0] keys: {list(paras[0].keys())}")
        ctx = paras[0].get("context", "")
        print(f"  data[0].paragraphs[0].context length: {len(ctx)} chars")
        print(f"  data[0].paragraphs[0].context preview: {ctx[:200]!r}")

        qas = paras[0].get("qas", [])
        print(f"  data[0].paragraphs[0].qas length: {len(qas)}")
        if qas:
            qa = qas[0]
            print(f"  data[0].paragraphs[0].qas[0] keys: {list(qa.keys())}")
            print(f"    id:            {qa.get('id')!r}")
            print(f"    question:      {qa.get('question', '')[:120]!r}")
            print(f"    is_impossible: {qa.get('is_impossible')}")
            answers = qa.get("answers", [])
            print(f"    answers length: {len(answers)}")
            if answers:
                print(f"    answers[0]: {answers[0]!r}")

    return data


# ---------------------------------------------------------------------------
# 3. QA inventory
# ---------------------------------------------------------------------------

def qa_inventory(data: list[dict]) -> None:
    section(3, "QA INVENTORY")

    total_qas = 0
    total_spans = 0
    total_impossible = 0
    qa_ids_global: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    qas_per_paragraph: Counter[int] = Counter()

    for contract in data:
        for para in contract.get("paragraphs", []):
            qas = para.get("qas", [])
            qas_per_paragraph[len(qas)] += 1
            for qa in qas:
                total_qas += 1
                qid = qa.get("id", "<no-id>")
                qa_ids_global[qid] += 1

                # Category is the suffix after "__" per CUAD convention
                if "__" in qid:
                    categories[qid.split("__", 1)[1]] += 1
                else:
                    categories["<no-category>"] += 1

                if qa.get("is_impossible"):
                    total_impossible += 1
                else:
                    total_spans += len(qa.get("answers", []))

    print(f"  Total QAs:                         {total_qas}")
    print(f"  Total answer spans (non-impossible): {total_spans}")
    print(f"  Total impossible QAs:              {total_impossible}")
    print(f"  Distinct QA IDs (global):          {len(qa_ids_global)}")

    dupes = [qid for qid, n in qa_ids_global.items() if n > 1]
    print(f"  QA IDs appearing >1 time globally: {len(dupes)}")
    if dupes:
        example = dupes[0]
        print(f"    Example duplicate: {example!r} (appears {qa_ids_global[example]} times)")

    print(f"  Distinct categories:               {len(categories)}")

    sub("QAs per paragraph (distribution)")
    for k in sorted(qas_per_paragraph):
        print(f"    {k:>3} QAs  ->  {qas_per_paragraph[k]} paragraphs")

    sub("Categories (QA count per category)")
    for cat, n in categories.most_common():
        print(f"    {n:>5}  {cat}")


# ---------------------------------------------------------------------------
# 4. Answer span integrity
# ---------------------------------------------------------------------------

def span_integrity(data: list[dict]) -> None:
    section(4, "ANSWER SPAN INTEGRITY")

    offset_ok = 0
    offset_bad = 0
    omitted_count = 0
    redacted_count = 0
    empty_count = 0
    offset_bad_examples: list[dict] = []
    omitted_examples: list[dict] = []
    redacted_examples: list[dict] = []

    for contract in data:
        title = contract.get("title", "<no-title>")
        for para in contract.get("paragraphs", []):
            context = para.get("context", "")
            for qa in para.get("qas", []):
                if qa.get("is_impossible"):
                    continue
                for ans in qa.get("answers", []):
                    text = ans.get("text", "")
                    start = ans.get("answer_start", -1)

                    if not text:
                        empty_count += 1
                        continue

                    has_omitted = OMITTED_TOKEN in text
                    has_redaction = any(m in text for m in REDACTION_MARKERS)

                    if has_omitted:
                        omitted_count += 1
                        if len(omitted_examples) < 3:
                            omitted_examples.append({
                                "title": title,
                                "qa_id": qa.get("id"),
                                "text": text[:200],
                            })
                    if has_redaction:
                        redacted_count += 1
                        if len(redacted_examples) < 3:
                            redacted_examples.append({
                                "title": title,
                                "qa_id": qa.get("id"),
                                "text": text[:200],
                            })

                    # Only verify offsets for spans without <omitted>
                    if not has_omitted:
                        actual = context[start:start + len(text)]
                        if actual == text:
                            offset_ok += 1
                        else:
                            offset_bad += 1
                            if len(offset_bad_examples) < 5:
                                offset_bad_examples.append({
                                    "title": title,
                                    "qa_id": qa.get("id"),
                                    "start": start,
                                    "expected": text[:120],
                                    "actual": actual[:120],
                                })

    print(f"  Spans with clean offset match:  {offset_ok}")
    print(f"  Spans with offset mismatch:     {offset_bad}")
    print(f"  Spans containing '<omitted>':   {omitted_count}")
    print(f"  Spans with redaction markers:   {redacted_count}")
    print(f"  Empty answer texts:             {empty_count}")

    if offset_bad_examples:
        sub("Offset mismatch examples")
        for ex in offset_bad_examples:
            print(f"    contract: {ex['title'][:80]}")
            print(f"    qa_id:    {ex['qa_id']}")
            print(f"    start:    {ex['start']}")
            print(f"    expected: {ex['expected']!r}")
            print(f"    actual:   {ex['actual']!r}")
            print()

    if omitted_examples:
        sub("'<omitted>' examples")
        for ex in omitted_examples:
            print(f"    {ex['title'][:60]} / {ex['qa_id']}")
            print(f"      {ex['text']!r}")

    if redacted_examples:
        sub("Redaction examples")
        for ex in redacted_examples:
            print(f"    {ex['title'][:60]} / {ex['qa_id']}")
            print(f"      {ex['text']!r}")


# ---------------------------------------------------------------------------
# 5. Paragraphs per contract
# ---------------------------------------------------------------------------

def paragraphs_per_contract(data: list[dict]) -> None:
    section(5, "PARAGRAPHS PER CONTRACT")

    counts: Counter[int] = Counter()
    for contract in data:
        counts[len(contract.get("paragraphs", []))] += 1

    print(f"  Contracts with exactly 1 paragraph:  {counts.get(1, 0)}")
    print(f"  Contracts with >1 paragraph:         {sum(v for k, v in counts.items() if k > 1)}")
    print(f"  Max paragraphs in any contract:      {max(counts) if counts else 0}")
    print(f"  Distinct paragraph counts observed:  {len(counts)}")

    sub("Histogram (paragraphs -> # contracts), top 20")
    for k in sorted(counts)[:20]:
        print(f"    {k:>4}  ->  {counts[k]}")


# ---------------------------------------------------------------------------
# 6. Worked sample of one contract
# ---------------------------------------------------------------------------

def sample_contract(data: list[dict], index: int = 0) -> None:
    section(6, f"SAMPLE CONTRACT (data[{index}])")

    c = data[index]
    print(f"  title:      {c.get('title')!r}")
    print(f"  paragraphs: {len(c.get('paragraphs', []))}")

    for pi, para in enumerate(c.get("paragraphs", [])[:2]):
        ctx = para.get("context", "")
        print(f"\n  --- paragraph[{pi}] ---")
        print(f"  context length: {len(ctx)} chars")
        print(f"  context preview: {ctx[:300]!r}")
        print(f"  qas length:      {len(para.get('qas', []))}")

        for qa in para.get("qas", [])[:3]:
            print(f"\n    QA id:         {qa.get('id')}")
            print(f"    is_impossible: {qa.get('is_impossible')}")
            print(f"    question:      {qa.get('question', '')[:120]!r}")
            answers = qa.get("answers", [])
            if answers:
                a = answers[0]
                print(f"    answer text:   {a.get('text', '')[:150]!r}")
                print(f"    answer_start:  {a.get('answer_start')}")
            else:
                print(f"    (no answers)")


# ---------------------------------------------------------------------------
# 7. JSON <-> TXT cross-check
# ---------------------------------------------------------------------------

def crosscheck_txt(data: list[dict]) -> None:
    section(7, "JSON <-> TXT CROSS-CHECK")

    if not TXT_DIR.exists():
        print(f"  TXT dir not found: {TXT_DIR}")
        return

    txt_files = {p.stem: p for p in TXT_DIR.glob("*.txt")}
    print(f"  TXT files found: {len(txt_files)}")

    matched = 0
    missing = 0
    length_close = 0
    length_far = 0
    missing_examples: list[str] = []

    for contract in data:
        title = contract.get("title", "")
        if title not in txt_files:
            missing += 1
            if len(missing_examples) < 5:
                missing_examples.append(title)
            continue

        matched += 1
        json_text = "".join(
            p.get("context", "") for p in contract.get("paragraphs", [])
        )
        txt_text = txt_files[title].read_text(encoding="utf-8", errors="replace")

        # Compare on whitespace-normalized lengths to tolerate formatting drift
        jn = len("".join(json_text.split()))
        tn = len("".join(txt_text.split()))
        if abs(jn - tn) <= max(200, 0.02 * tn):
            length_close += 1
        else:
            length_far += 1

    print(f"  Contracts with a matching TXT:      {matched}")
    print(f"  Contracts missing a TXT:            {missing}")
    print(f"  Lengths close (within ~2%):         {length_close}")
    print(f"  Lengths differ (>2%):               {length_far}")

    if missing_examples:
        sub("Example missing TXT titles")
        for t in missing_examples:
            print(f"    {t!r}")


# ---------------------------------------------------------------------------
# 8. master_clauses.csv inspection
# ---------------------------------------------------------------------------

def inspect_csv() -> None:
    section(8, "master_clauses.csv INSPECTION")

    if not CSV_PATH.exists():
        print(f"  CSV not found: {CSV_PATH}")
        return

    try:
        import pandas as pd
    except ImportError:
        print("  pandas not installed; skipping CSV inspection.")
        return

    try:
        df = pd.read_csv(CSV_PATH, nrows=3)
    except Exception as e:
        print(f"  Error reading CSV: {e}")
        return

    print(f"  Columns ({len(df.columns)}):")
    for i, col in enumerate(df.columns):
        print(f"    [{i:>2}] {col!r}")

    sub("First row (first 8 columns)")
    for col in df.columns[:8]:
        val = str(df.iloc[0][col])
        print(f"    {col!r}: {val[:140]!r}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not check_files():
        print("\nSome required files are missing. Continuing anyway...")

    payload = load_json()
    data = inspect_top_level(payload)

    qa_inventory(data)
    span_integrity(data)
    paragraphs_per_contract(data)
    sample_contract(data, index=0)
    crosscheck_txt(data)
    inspect_csv()


if __name__ == "__main__":
    main()