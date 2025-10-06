import csv
import importlib.util
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
METRICS_PATH = ROOT_DIR / "app" / "utils" / "metrics.py"
SPEC = importlib.util.spec_from_file_location("metrics_module", METRICS_PATH)
assert SPEC and SPEC.loader
metrics_module = importlib.util.module_from_spec(SPEC)
sys.modules["metrics_module"] = metrics_module
SPEC.loader.exec_module(metrics_module)
MetricsLogger = metrics_module.MetricsLogger


def test_metrics_logger_expands_header(tmp_path):
    csv_path = tmp_path / "metrics.csv"
    logger = MetricsLogger(csv_path=csv_path)

    base_payload = {
        "service": "svc",
        "operation": "op",
        "model": "model-name",
    }

    logger.log(base_payload)
    logger.log({**base_payload, "new_metadata": "value"})

    with csv_path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames is not None
        assert "meta_new_metadata" in reader.fieldnames
        rows = list(reader)

    assert rows[0]["meta_new_metadata"] == ""
    assert rows[1]["meta_new_metadata"] == "value"
