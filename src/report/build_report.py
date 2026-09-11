"""
build_report.py — Render and compile a single-contract LaTeX report.

Reads a scorecard from the analysis database, renders the Jinja2 template,
writes a .tex file, compiles it with xelatex, and moves the resulting PDF
into reports/pdf/.

Errors during compilation are reported with a pointer to the log file.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.paths import FIGURES_DIR, LATEX_DIR, PDF_DIR, PROJECT_ROOT, REPORTS_DIR
from src.db import dao


TEMPLATE_DIR = Path(__file__).parent
BUILD_DIR = REPORTS_DIR / "build"


# ---------------------------------------------------------------------------
# Jinja2 environment
# ---------------------------------------------------------------------------

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    block_start_string="<<",
    block_end_string=">>",
    variable_start_string="<{",
    variable_end_string="}>",
    comment_start_string="<#",
    comment_end_string="#>",
    trim_blocks=True,
    lstrip_blocks=True,
    autoescape=select_autoescape(enabled_extensions=(), default=False),
)


# Sentinel used to protect backslashes during escaping. \x00 does not
# appear in contract text and cannot be produced by any other step.
_BACKSLASH_PLACEHOLDER = "\x00"

_TEX_REPLACEMENTS = (
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
)


def tex_escape(value) -> str:
    if value is None:
        return ""
    # Collapse all whitespace (spaces, tabs, newlines, carriage returns)
    # to single spaces. Span-derived evidence text from CUAD can contain
    # blank lines, which LaTeX interprets as \par. Commands like \textit
    # and \textbf reject \par inside their argument, so this normalization
    # is required before any escaping is applied.
    s = " ".join(str(value).split())
    s = s.replace("\\", _BACKSLASH_PLACEHOLDER)
    for old, new in _TEX_REPLACEMENTS:
        s = s.replace(old, new)
    s = s.replace(_BACKSLASH_PLACEHOLDER, r"\textbackslash{}")
    return s

_env.filters["tex_escape"] = tex_escape


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _short_id(contract_id: str, limit: int = 70) -> str:
    if len(contract_id) <= limit:
        return contract_id
    return contract_id[: limit - 3] + "..."


def _safe_filename(name: str, max_len: int = 140) -> str:
    keep = []
    for ch in name:
        if ch in '<>:"/\\|?*\x00' or ord(ch) < 32:
            keep.append("_")
        else:
            keep.append(ch)
    s = "".join(keep).strip()
    if len(s) > max_len:
        s = s[:max_len].rstrip()
    return s or "report"


def _severity_display(sev: str) -> str:
    return {
        "high": "High",
        "medium": "Medium",
        "low": "Low",
    }.get(sev, sev.title())


def _liability_display(state: str) -> str:
    return {
        "capped":        "Capped",
        "uncapped":      "Uncapped",
        "contradictory": "Contradictory",
        "silent":        "Silent",
    }.get(state, state.title())


def _summary_sentence(card: dict) -> str:
    score = card["contract"]["score"]
    sev = {}
    for f in card["findings"]:
        sev[f["severity"]] = sev.get(f["severity"], 0) + 1
    parts = [f"{sev.get('high', 0)} high-severity",
             f"{sev.get('medium', 0)} medium-severity",
             f"{sev.get('low', 0)} low-severity"]
    return (
        f"This contract scored {score} of 100 and presents "
        + ", ".join(parts) + " findings for review."
    )


def _liability_note(card: dict) -> str:
    liab = card["contract"].get("liability_state", "")
    note = card.get("lifecycle") or {}
    # Liability note text comes from the scorecard's findings table, where
    # the Liability Exposure row carries the note. If not present, fall
    # back to a generic sentence per state.
    for f in card["findings"]:
        if f["category"] == "Liability Exposure":
            return tex_escape(f["rationale"])
    fallback = {
        "capped":        "A liability cap is present and no uncapped language was detected. Standard posture.",
        "uncapped":      "Explicit uncapped liability language is present with no corresponding cap.",
        "contradictory": "Both a cap and uncapped language appear in the contract. An attorney must reconcile scope.",
        "silent":        "Neither a liability cap nor uncapped language appears in the contract text. Exposure depends on default rules.",
    }
    return tex_escape(fallback.get(liab, "Liability posture not classified."))


def _corpus_stats() -> dict:
    """Corpus-level numbers used in the methodology section."""
    try:
        contracts = dao.top_contracts_by_score(limit=1000)
        n_multi = sum(1 for c in contracts if c.get("group_id"))
        n_redacted = sum(1 for c in contracts if c.get("has_redactions"))
        return {"n_multi_part_corpus": n_multi, "n_redacted_corpus": n_redacted}
    except Exception:
        return {"n_multi_part_corpus": 0, "n_redacted_corpus": 0}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def _parse_sibling_ids(contract: dict) -> list[str]:
    """sibling_ids is stored as a JSON-encoded string in the database."""
    raw = contract.get("sibling_ids")
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
        return list(parsed) if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


def _n_parts(contract: dict) -> int:
    return len(_parse_sibling_ids(contract)) + 1
def _assemble_context(card: dict) -> dict:
    contract = card["contract"]
    lc = card.get("lifecycle") or {}
    findings = card.get("findings") or []
    inventory = card.get("inventory") or {"present": [], "absent": []}

    corpus = _corpus_stats()
    ref = contract.get("reference_date") or "none"

    return {
        "contract_id": contract["contract_id"],
        "short_id": _short_id(contract["contract_id"]),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "score": contract["score"],
        "liability_display": _liability_display(contract.get("liability_state", "")),
        "liability_note": _liability_note(card),
        "summary_sentence": tex_escape(_summary_sentence(card)),
        "n_high": sum(1 for f in findings if f["severity"] == "high"),
        "n_medium": sum(1 for f in findings if f["severity"] == "medium"),
        "n_low": sum(1 for f in findings if f["severity"] == "low"),
        "lc": {
            "agreement_date": lc.get("agreement_date"),
            "effective_date": lc.get("effective_date"),
            "expiration_date": lc.get("expiration_date"),
            "renewal_term": lc.get("renewal_term"),
            "notice_period": lc.get("notice_period"),
            "narrative": tex_escape(lc.get("narrative", "")),
            "missing": [tex_escape(c) for c in lc.get("missing_categories_parsed", [])],
            "missing_but_span_present": [
                tex_escape(c) for c in lc.get("missing_but_span_present_parsed", [])
            ],
        },
        "is_multi_part": bool(contract.get("group_id")),
        "part_number": contract.get("part_number"),
        "n_parts": _n_parts(contract),
        "sibling_ids": _parse_sibling_ids(contract),
        "has_redactions": bool(contract.get("has_redactions")),
        "redaction_count": contract.get("redaction_count", 0),
        "findings": findings,
        "present_categories": inventory["present"],
        "absent_categories": inventory["absent"],
        "n_present": len(inventory["present"]),
        "n_absent": len(inventory["absent"]),
        "n_multi_part_corpus": corpus["n_multi_part_corpus"],
        "n_redacted_corpus": corpus["n_redacted_corpus"],
        "reference_note": (
            "The report was generated without a reference date. Expiration-based findings "
            "do not fire unless a reference date is supplied with --as-of."
            if ref == "none"
            else f"Expiration findings were evaluated against {ref}."
        ),
    }


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------

def _run_xelatex(tex_path: Path, output_dir: Path) -> tuple[bool, str, str]:
    """
    Run xelatex twice (for references). Return (success, log_path, tail).
    The tail is the last 30 lines of the log, useful for surfacing the
    actual error to the console.
    """
    if shutil.which("xelatex") is None:
        raise RuntimeError(
            "xelatex not found on PATH. Install TeX Live or MacTeX, "
            "or invoke with --no-compile to only emit .tex."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / f"{tex_path.stem}.log"

    for _ in range(2):
        proc = subprocess.run(
            [
                "xelatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                f"-output-directory={output_dir}",
                str(tex_path),
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            tail = ""
            if log_path.exists():
                try:
                    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    tail = "\n".join(lines[-30:])
                except Exception:
                    tail = "(could not read log)"
            return False, str(log_path), tail

    return True, str(log_path), ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_contract(contract_id: str, compile_pdf: bool = True) -> dict:
    """
    Render a single contract report. Returns a dict with paths and status.
    """
    
    card = dao.get_scorecard(contract_id)
    if card is None:
        return {"status": "not_found", "contract_id": contract_id}
    # The DAO returns raw JSON strings for missing lists; parse them.
    lc = card.get("lifecycle") or {}
    if isinstance(lc.get("missing_categories"), str):
        import json as _json
        try:
            lc["missing_categories_parsed"] = _json.loads(lc["missing_categories"])
        except Exception:
            lc["missing_categories_parsed"] = []
    else:
        lc["missing_categories_parsed"] = lc.get("missing_categories") or []

    if isinstance(lc.get("missing_but_span_present"), str):
        import json as _json
        try:
            lc["missing_but_span_present_parsed"] = _json.loads(
                lc["missing_but_span_present"]
            )
        except Exception:
            lc["missing_but_span_present_parsed"] = []
    else:
        lc["missing_but_span_present_parsed"] = lc.get("missing_but_span_present") or []

    card["lifecycle"] = lc

    context = _assemble_context(card)
    template = _env.get_template("template.tex.j2")
    rendered = template.render(**context)

    safe = _safe_filename(contract_id)
    # Remove any stray PDF from the LaTeX directory for this contract.
    # xelatex only writes to BUILD_DIR when invoked by this script, but a
    # manual invocation can leave a stale PDF here.
    stray_pdf = LATEX_DIR / f"{safe}.pdf"
    if stray_pdf.exists():
        stray_pdf.unlink()
    LATEX_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    tex_path = LATEX_DIR / f"{safe}.tex"
    tex_path.write_text(rendered, encoding="utf-8")

    result = {
        "status": "ok",
        "contract_id": contract_id,
        "tex_path": str(tex_path),
        "pdf_path": None,
        "log_path": None,
    }

    if not compile_pdf:
        return result

    success, log_path, tail = _run_xelatex(tex_path, BUILD_DIR)
    result["log_path"] = log_path

    if not success:
        result["status"] = "compile_failed"
        result["log_tail"] = tail
        return result

    built_pdf = BUILD_DIR / f"{tex_path.stem}.pdf"
    if not built_pdf.exists():
        result["status"] = "no_pdf_produced"
        return result

    final_pdf = PDF_DIR / f"{tex_path.stem}.pdf"
    shutil.move(str(built_pdf), str(final_pdf))
    result["pdf_path"] = str(final_pdf)
    return result


def render_group(group_id: str, compile_pdf: bool = True) -> dict:
    """
    Placeholder for Option D group-level reports. Not yet implemented.

    This is the intended entry point when group reports are added: it will
    read the group's merged findings from dao.get_group_findings and feed
    them through the same template with is_multi_part=True and
    sibling_ids=[] so the callout renders the group header.
    """
    raise NotImplementedError(
        "Group-level reports are not yet implemented. "
        "Use render_contract for individual parts."
    )