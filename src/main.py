from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any

import pandas as pd

from .data_anomaly_detect import build_anomaly_candidates
from .console_utf8 import setup_console_utf8
from .data_ingest import build_standardized_market_data
from .dashboard_data import build_dashboard_payload
from .dashboard_agent_insights import build_dashboard_agent_insights_from_file
from .agent_insight_generate import build_report_insights
from .pipeline_contract import get_artifact_filenames, get_pipeline_step_names, load_pipeline_contract
from .report_render import write_docx_report
from .data_rules_config import load_rules_config
from .report_schema_contracts import validate_report_insights
from .data_weekly_calc import bind_monitor_change_field, build_weekly_changes, build_weekly_metrics


def _ensure_parent(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _load_standardized_input(path: str) -> pd.DataFrame:
    inp = pd.read_csv(path, encoding="utf-8", low_memory=False)
    if "is_valid" in inp.columns:
        inp = inp[inp["is_valid"].astype(str).str.lower() == "true"].copy()
    inp["date"] = pd.to_datetime(inp["date"], errors="coerce")
    return inp


def _build_weekly_metrics_artifact(input_path: str) -> pd.DataFrame:
    inp = _load_standardized_input(input_path)
    return build_weekly_metrics(inp)


def _build_weekly_changes_artifact(
    weekly_metrics_path: str,
    rules_config_path: str,
    metric_rule_mapping_path: str,
) -> pd.DataFrame:
    weekly_metrics = pd.read_csv(weekly_metrics_path, encoding="utf-8", low_memory=False)
    rules_cfg = load_rules_config(rules_config_path)
    weekly_changes = build_weekly_changes(weekly_metrics)
    return bind_monitor_change_field(
        weekly_changes,
        rules_cfg=rules_cfg,
        metric_rule_mapping_path=metric_rule_mapping_path,
    )


def _resolve_target_week_start(weekly_changes: pd.DataFrame, requested_week_start: str | None = None) -> pd.Timestamp | pd.NaT:
    if requested_week_start:
        return pd.to_datetime(requested_week_start, errors="coerce")

    today = pd.Timestamp.now().normalize()
    completed_weeks = weekly_changes.loc[weekly_changes["week_end"] < today, "week_start"].dropna()
    if not completed_weeks.empty:
        return completed_weeks.max()
    return weekly_changes["week_start"].dropna().max()


def run_ingest(args: argparse.Namespace) -> None:
    out_df = build_standardized_market_data(args.input, args.mapping)
    _ensure_parent(args.out)
    out_df.to_csv(args.out, index=False, encoding="utf-8")


def run_weekly_metrics_step(args: argparse.Namespace) -> None:
    weekly_metrics = _build_weekly_metrics_artifact(args.input)
    _ensure_parent(args.out)
    weekly_metrics.to_csv(args.out, index=False, encoding="utf-8")


def run_weekly_changes_step(args: argparse.Namespace) -> None:
    weekly_changes = _build_weekly_changes_artifact(
        weekly_metrics_path=args.metrics,
        rules_config_path=args.rules_config,
        metric_rule_mapping_path=args.metric_rule_mapping,
    )
    _ensure_parent(args.out)
    weekly_changes.to_csv(args.out, index=False, encoding="utf-8")


def run_weekly_calc(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    weekly_metrics_path = out_dir / "weekly_metrics.csv"
    weekly_changes_path = out_dir / "weekly_changes.csv"
    run_weekly_metrics_step(argparse.Namespace(input=args.input, out=str(weekly_metrics_path)))
    run_weekly_changes_step(
        argparse.Namespace(
            metrics=str(weekly_metrics_path),
            out=str(weekly_changes_path),
            rules_config=args.rules_config,
            metric_rule_mapping=args.metric_rule_mapping,
        )
    )


def run_anomaly_detect(args: argparse.Namespace) -> None:
    weekly_changes = pd.read_csv(args.input, encoding="utf-8", low_memory=False)
    weekly_changes["week_start"] = pd.to_datetime(weekly_changes["week_start"], errors="coerce")
    weekly_changes["week_end"] = pd.to_datetime(weekly_changes["week_end"], errors="coerce")
    candidates = build_anomaly_candidates(
        weekly_changes,
        rules_cfg_path=args.rules_config,
        metric_rule_mapping_path=args.metric_rule_mapping,
    )
    _ensure_parent(args.out)
    candidates.to_csv(args.out, index=False, encoding="utf-8")


def run_insight_generate(args: argparse.Namespace) -> None:
    weekly_changes = pd.read_csv(args.changes, encoding="utf-8", low_memory=False)
    try:
        anomaly_candidates = pd.read_csv(args.candidates, encoding="utf-8", low_memory=False)
    except pd.errors.EmptyDataError:
        anomaly_candidates = pd.DataFrame()

    weekly_changes["week_start"] = pd.to_datetime(weekly_changes["week_start"], errors="coerce")
    weekly_changes["week_end"] = pd.to_datetime(weekly_changes["week_end"], errors="coerce")
    target_week_start = _resolve_target_week_start(weekly_changes, requested_week_start=args.target_week_start)

    if pd.isna(target_week_start):
        week_start = str(pd.Timestamp.today().date())
    else:
        week_start = str(target_week_start.date())

    if not anomaly_candidates.empty and not pd.isna(target_week_start):
        anomaly_candidates["week_start"] = pd.to_datetime(anomaly_candidates["week_start"], errors="coerce")
        anomaly_candidates = anomaly_candidates[anomaly_candidates["week_start"] == target_week_start]

    insights = build_report_insights(
        week_start=week_start,
        top_n=args.top_n,
        anomaly_candidates=anomaly_candidates,
        weekly_changes=weekly_changes,
        enable_external_search=args.enable_external_search,
    )
    validate_report_insights(insights)
    _ensure_parent(args.out)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(insights, f, ensure_ascii=False, indent=2, default=str)


def run_render_report(args: argparse.Namespace) -> None:
    with open(args.insights, "r", encoding="utf-8") as f:
        insights = json.load(f)

    validate_report_insights(insights)
    write_docx_report(insights, args.docx)


def run_dashboard_data(args: argparse.Namespace) -> None:
    standardized = _load_standardized_input(args.input)
    payload = build_dashboard_payload(
        standardized,
        latest_date=getattr(args, "latest_date", None),
        top_n=getattr(args, "top_n", 10),
    )
    _ensure_parent(args.out)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)


def run_agent_insights(args: argparse.Namespace) -> None:
    build_dashboard_agent_insights_from_file(
        dashboard_data_path=args.dashboard_data,
        out_path=args.out,
        top_n=args.top_n,
        enable_external_search=args.enable_external_search,
        target_date=args.target_date,
    )


def run_dashboard(args: argparse.Namespace) -> None:
    artifact_dir = Path(getattr(args, "artifact_dir", "artifacts"))
    frontend_dir = Path(getattr(args, "frontend_dir", "frontend"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    dashboard_out = frontend_dir / "data" / "dashboard_data.json"
    standardized = artifact_dir / "standardized_market_data.csv"

    run_ingest(argparse.Namespace(input=args.input, mapping=args.mapping, out=str(standardized)))
    run_dashboard_data(
        argparse.Namespace(
            input=str(standardized),
            out=str(dashboard_out),
            latest_date=getattr(args, "latest_date", None),
            top_n=getattr(args, "top_n", 10),
        )
    )


def run_all(args: argparse.Namespace) -> None:
    pipeline_contract = load_pipeline_contract(args.pipeline_contract)
    pipeline_steps = get_pipeline_step_names(pipeline_contract)

    artifact_dir = Path(args.artifact_dir)
    output_dir = Path(args.output_dir)
    frontend_dir = Path(getattr(args, "frontend_dir", "frontend"))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    filenames = get_artifact_filenames(pipeline_contract)
    standardized = artifact_dir / filenames.get("standardized_market_data", "standardized_market_data.csv")
    weekly_metrics = artifact_dir / filenames.get("weekly_metrics", "weekly_metrics.csv")
    weekly_changes = artifact_dir / filenames.get("weekly_changes", "weekly_changes.csv")
    anomaly_candidates = artifact_dir / filenames.get("anomaly_candidates", "anomaly_candidates.csv")
    insights_json = artifact_dir / filenames.get("report_insights", "report_insights.json")
    docx_out = output_dir / filenames.get("weekly_report", "weekly_report.docx")
    dashboard_json = frontend_dir / "data" / filenames.get("dashboard_data", "dashboard_data.json")

    step_handlers: dict[str, tuple[Any, argparse.Namespace]] = {
        "ingest_standardize": (
            run_ingest,
            argparse.Namespace(input=args.input, mapping=args.mapping, out=str(standardized)),
        ),
        "build_weekly_metrics": (
            run_weekly_metrics_step,
            argparse.Namespace(input=str(standardized), out=str(weekly_metrics)),
        ),
        "build_weekly_changes": (
            run_weekly_changes_step,
            argparse.Namespace(
                metrics=str(weekly_metrics),
                out=str(weekly_changes),
                rules_config=args.rules_config,
                metric_rule_mapping=args.metric_rule_mapping,
            ),
        ),
        "detect_anomalies": (
            run_anomaly_detect,
            argparse.Namespace(
                input=str(weekly_changes),
                out=str(anomaly_candidates),
                rules_config=args.rules_config,
                metric_rule_mapping=args.metric_rule_mapping,
            ),
        ),
        "generate_insights": (
            run_insight_generate,
            argparse.Namespace(
                changes=str(weekly_changes),
                candidates=str(anomaly_candidates),
                out=str(insights_json),
                top_n=args.top_n,
                enable_external_search=args.enable_external_search,
                target_week_start=args.target_week_start,
            ),
        ),
        "render_report": (
            run_render_report,
            argparse.Namespace(
                insights=str(insights_json),
                docx=str(docx_out),
            ),
        ),
        "build_dashboard_data": (
            run_dashboard_data,
            argparse.Namespace(
                input=str(standardized),
                out=str(dashboard_json),
                latest_date=getattr(args, "latest_date", None),
                top_n=getattr(args, "top_n", 10),
            ),
        ),
    }

    unknown_steps = [step_name for step_name in pipeline_steps if step_name not in step_handlers]
    if unknown_steps:
        raise ValueError(f"pipeline contract contains unsupported steps: {', '.join(unknown_steps)}")

    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")
    run_date = datetime.now(timezone.utc).isoformat()
    status_rows: list[dict[str, object]] = []

    def exec_step(step_name: str, fn: Any, step_args: argparse.Namespace) -> None:
        start = time.time()
        status = "ok"
        err = ""
        try:
            fn(step_args)
        except Exception as ex:
            status = "failed"
            err = str(ex)
            raise
        finally:
            status_rows.append(
                {
                    "run_id": run_id,
                    "run_date": run_date,
                    "target_week_start": getattr(args, "target_week_start", None) or "",
                    "target_week_end": "",
                    "step_name": step_name,
                    "status": status,
                    "duration_sec": round(time.time() - start, 3),
                    "error_code": "" if status == "ok" else "runtime_error",
                    "error_message": err,
                    "version_tag": "pipeline_contract_v1",
                }
            )

    try:
        for step_name in pipeline_steps:
            fn, step_args = step_handlers[step_name]
            exec_step(step_name, fn, step_args)
    finally:
        log_path = Path("logs/run_status_log.csv")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        new_df = pd.DataFrame(status_rows)
        if log_path.exists():
            old_df = pd.read_csv(log_path, encoding="utf-8", low_memory=False)
            all_df = pd.concat([old_df, new_df], ignore_index=True)
        else:
            all_df = new_df
        all_df.to_csv(log_path, index=False, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Market dashboard pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("run_ingest")
    p_ingest.add_argument("--input", required=True)
    p_ingest.add_argument("--mapping", default="config/sheet_contracts.yaml")
    p_ingest.add_argument("--out", required=True)
    p_ingest.set_defaults(func=run_ingest)

    p_weekly_metrics = sub.add_parser("run_weekly_metrics")
    p_weekly_metrics.add_argument("--input", required=True)
    p_weekly_metrics.add_argument("--out", required=True)
    p_weekly_metrics.set_defaults(func=run_weekly_metrics_step)

    p_weekly_changes = sub.add_parser("run_weekly_changes")
    p_weekly_changes.add_argument("--metrics", required=True)
    p_weekly_changes.add_argument("--out", required=True)
    p_weekly_changes.add_argument("--rules-config", default="config/rules_config.yaml")
    p_weekly_changes.add_argument("--metric-rule-mapping", default="config/metric_rule_mapping.yaml")
    p_weekly_changes.set_defaults(func=run_weekly_changes_step)

    p_weekly = sub.add_parser("run_weekly_calc")
    p_weekly.add_argument("--input", required=True)
    p_weekly.add_argument("--out-dir", required=True)
    p_weekly.add_argument("--rules-config", default="config/rules_config.yaml")
    p_weekly.add_argument("--metric-rule-mapping", default="config/metric_rule_mapping.yaml")
    p_weekly.set_defaults(func=run_weekly_calc)

    p_anom = sub.add_parser("run_anomaly_detect")
    p_anom.add_argument("--input", required=True)
    p_anom.add_argument("--out", required=True)
    p_anom.add_argument("--rules-config", default="config/rules_config.yaml")
    p_anom.add_argument("--metric-rule-mapping", default="config/metric_rule_mapping.yaml")
    p_anom.set_defaults(func=run_anomaly_detect)

    p_insight = sub.add_parser("run_insight_generate")
    p_insight.add_argument("--changes", required=True)
    p_insight.add_argument("--candidates", required=True)
    p_insight.add_argument("--out", required=True)
    p_insight.add_argument("--top-n", type=int, default=10)
    p_insight.add_argument("--enable-external-search", action=argparse.BooleanOptionalAction, default=True)
    p_insight.add_argument("--target-week-start", default=None)
    p_insight.set_defaults(func=run_insight_generate)

    p_report = sub.add_parser("run_render_report")
    p_report.add_argument("--insights", required=True)
    p_report.add_argument("--docx", required=True)
    p_report.set_defaults(func=run_render_report)

    p_dashboard_data = sub.add_parser("run_dashboard_data")
    p_dashboard_data.add_argument("--input", required=True)
    p_dashboard_data.add_argument("--out", default="frontend/data/dashboard_data.json")
    p_dashboard_data.add_argument("--latest-date", default=None)
    p_dashboard_data.add_argument("--top-n", type=int, default=10)
    p_dashboard_data.set_defaults(func=run_dashboard_data)

    p_agent_insights = sub.add_parser("run_agent_insights")
    p_agent_insights.add_argument("--dashboard-data", default="frontend/data/dashboard_data.json")
    p_agent_insights.add_argument("--out", default="frontend/data/agent_insights.json")
    p_agent_insights.add_argument("--top-n", type=int, default=5)
    p_agent_insights.add_argument("--target-date", default=None)
    p_agent_insights.add_argument("--enable-external-search", action=argparse.BooleanOptionalAction, default=True)
    p_agent_insights.set_defaults(func=run_agent_insights)

    p_dashboard = sub.add_parser("run_dashboard")
    p_dashboard.add_argument("--input", required=True)
    p_dashboard.add_argument("--mapping", default="config/sheet_contracts.yaml")
    p_dashboard.add_argument("--artifact-dir", default="artifacts")
    p_dashboard.add_argument("--frontend-dir", default="frontend")
    p_dashboard.add_argument("--latest-date", default=None)
    p_dashboard.add_argument("--top-n", type=int, default=10)
    p_dashboard.set_defaults(func=run_dashboard)

    p_all = sub.add_parser("run_all")
    p_all.add_argument("--input", required=True)
    p_all.add_argument("--mapping", default="config/sheet_contracts.yaml")
    p_all.add_argument("--rules-config", default="config/rules_config.yaml")
    p_all.add_argument("--metric-rule-mapping", default="config/metric_rule_mapping.yaml")
    p_all.add_argument("--pipeline-contract", default="config/pipeline_contract.yaml")
    p_all.add_argument("--artifact-dir", default="artifacts")
    p_all.add_argument("--output-dir", default="outputs")
    p_all.add_argument("--frontend-dir", default="frontend")
    p_all.add_argument("--latest-date", default=None)
    p_all.add_argument("--top-n", type=int, default=10)
    p_all.add_argument("--enable-external-search", action=argparse.BooleanOptionalAction, default=True)
    p_all.add_argument("--target-week-start", default=None)
    p_all.set_defaults(func=run_all)

    return parser


def main() -> None:
    setup_console_utf8()
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
