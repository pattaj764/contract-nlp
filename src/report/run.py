"""
run.py — CLI for building LaTeX reports.

Usage:
    python -m src.report.run --contract <contract_id>
    python -m src.report.run --top 5
    python -m src.report.run --all
    python -m src.report.run --contract <id> --no-compile
    python -m src.report.run --group <group_id>     (not yet implemented)
"""

from __future__ import annotations

import argparse
import sys

from src.db import dao
from src.report.build_report import render_contract


def _print_result(r: dict) -> None:
    status = r.get("status")
    cid = r.get("contract_id", "")
    short = cid[:70] + ("..." if len(cid) > 70 else "")

    if status == "ok":
        print(f"  [ok]            {short}")
        print(f"                  tex: {r['tex_path']}")
        if r.get("pdf_path"):
            print(f"                  pdf: {r['pdf_path']}")
    elif status == "compile_failed":
        print(f"  [compile fail]  {short}")
        print(f"                  log: {r.get('log_path')}")
        if r.get("log_tail"):
            print()
            for line in r["log_tail"].splitlines():
                print(f"    | {line}")
    elif status == "not_found":
        print(f"  [not found]     {short}")
    else:
        print(f"  [{status}]  {short}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=str, default=None,
                        help="Build a report for one contract by ID")
    parser.add_argument("--group", type=str, default=None,
                        help="Build a group-level report (not yet implemented)")
    parser.add_argument("--top", type=int, default=None,
                        help="Build reports for the N highest-scoring contracts")
    parser.add_argument("--all", action="store_true",
                        help="Build reports for all contracts")
    parser.add_argument("--no-compile", action="store_true",
                        help="Only emit .tex files; do not run xelatex")
    args = parser.parse_args()

    compile_pdf = not args.no_compile

    if args.group:
        print("Group-level reports are not yet implemented.")
        sys.exit(1)

    if args.contract:
        r = render_contract(args.contract, compile_pdf=compile_pdf)
        _print_result(r)
        if r["status"] not in ("ok",):
            sys.exit(1)
        return

    if args.top:
        contracts = dao.top_contracts_by_score(limit=args.top)
        for c in contracts:
            _print_result(render_contract(c["contract_id"], compile_pdf=compile_pdf))
        return

    if args.all:
        contracts = dao.top_contracts_by_score(limit=1000)
        n_ok = 0
        n_fail = 0
        for c in contracts:
            r = render_contract(c["contract_id"], compile_pdf=compile_pdf)
            _print_result(r)
            if r["status"] == "ok":
                n_ok += 1
            else:
                n_fail += 1
        print(f"\nCompleted: {n_ok} ok, {n_fail} failed.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
