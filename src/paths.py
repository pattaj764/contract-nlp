"""paths.py — Central project path definitions.

Keeping these in one place avoids circular-import surprises and makes it
trivial to relocate the dataset or re-root the project.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CUAD_DIR = RAW_DIR / "CUAD_v1"

JSON_PATH = CUAD_DIR / "CUAD_v1.json"
CSV_PATH = CUAD_DIR / "master_clauses.csv"
TXT_DIR = CUAD_DIR / "full_contract_txt"

PROCESSED_DIR = DATA_DIR / "processed"
CONTRACTS_DIR = PROCESSED_DIR / "contracts"
CLAUSES_JSONL = PROCESSED_DIR / "clauses.jsonl"
ABSENCES_JSONL = PROCESSED_DIR / "absences.jsonl"
ANSWERS_CSV = PROCESSED_DIR / "answers.csv"
REPORT_PATH = PROCESSED_DIR / "ingestion_report.json"
CONTRACT_METADATA_JSONL = PROCESSED_DIR / "contract_metadata.jsonl"
SCORED_DIR = PROCESSED_DIR / "scored"

REPORTS_DIR = PROJECT_ROOT / "reports"
DB_PATH = REPORTS_DIR / "analysis.db"
LATEX_DIR = REPORTS_DIR / "latex"
PDF_DIR = REPORTS_DIR / "pdf"
FIGURES_DIR = REPORTS_DIR / "figures"