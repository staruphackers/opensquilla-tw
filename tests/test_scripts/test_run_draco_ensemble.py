from __future__ import annotations

import asyncio
import json
from argparse import Namespace
from pathlib import Path

import pytest

from opensquilla.gateway.config import GatewayConfig
from opensquilla.provider.selector import ProviderConfig
from opensquilla.provider.types import DoneEvent, Message, TextDeltaEvent
from scripts.run_draco_ensemble import (
    GROUP_SPECS,
    amain,
    build_parser,
    build_profile_provider,
    collect_run,
    group_timeout_seconds,
    judge_text,
    load_tasks,
    quality_total,
    render_markdown,
    score_criterion_judgments,
    summarize,
)


class _CriterionJudgeProvider:
    model = "judge-test"
    provider_name = "judge"

    async def chat(self, messages: list[Message], tools=None, config=None):  # noqa: ANN001
        prompt = str(messages[-1].content)
        verdict = "UNMET" if "type: negative" in prompt else "MET"
        yield TextDeltaEvent(
            text=f'```json\n{{"verdict":"{verdict}","rationale":"ok"}}\n```'
        )
        yield DoneEvent(model=self.model)

    async def list_models(self) -> list:
        return []


class _SlowProvider:
    provider_name = "slow"

    async def chat(self, messages: list[Message], tools=None, config=None):  # noqa: ANN001
        await asyncio.sleep(1.0)
        yield TextDeltaEvent(text="late")
        yield DoneEvent(model="slow")

    async def list_models(self) -> list:
        return []


@pytest.mark.asyncio
async def test_draco_runner_dry_run_writes_jsonl_and_summary(tmp_path: Path) -> None:
    input_path = tmp_path / "draco.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "id": "task-1",
                "prompt": "Explain the evidence carefully.",
                "domain": "science",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "reports"
    args = Namespace(
        input=input_path,
        config=None,
        output_dir=output_dir,
        groups="B2,G1,G3",
        max_tasks=0,
        concurrency=2,
        timeout=10.0,
        dry_run=True,
        judge_model="dry-judge",
        judge_repeats=1,
        judge_concurrency=1,
        judge_candidates=True,
    )

    rc = await amain(args)

    assert rc == 0
    [jsonl_path] = output_dir.glob("draco_ensemble_*.jsonl")
    rows = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert {row["group"] for row in rows} == {"B2", "G1", "G3"}
    g1 = next(row for row in rows if row["group"] == "G1")
    assert g1["ensemble_trace"]["profile"] == "g1_code"
    g3 = next(row for row in rows if row["group"] == "G3")
    assert g3["ensemble_trace"]["profile"] == "g3_standard"
    assert g3["candidate_judges"]
    assert g3["usage"]["model_usage_breakdown"]
    assert g3["run_trace"]["event_count"] >= 2
    assert g3["final_text_sha256"]
    md_path = jsonl_path.with_suffix(".md")
    assert "DRACO Ensemble Summary" in md_path.read_text(encoding="utf-8")
    summary_json_path = jsonl_path.with_suffix(".summary.json")
    assert summary_json_path.exists()
    [trace_path] = output_dir.glob("draco_run_*.trace.jsonl")
    trace_rows = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(trace_rows) == len(rows)
    assert trace_rows[0]["run_trace"]["events"]
    [manifest_path] = output_dir.glob("draco_run_*.manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert manifest["rows_written"] == len(rows)
    assert manifest["artifacts"]["trace_jsonl"] == str(trace_path)


def test_draco_runner_default_groups_include_g1() -> None:
    args = build_parser().parse_args(["--input", "draco.jsonl"])

    assert "G1" in args.groups.split(",")
    assert GROUP_SPECS["G1"]["profile"] == "g1_code"
    assert args.judge_concurrency == 1


def test_draco_runner_profile_groups_exist_in_default_config() -> None:
    cfg = GatewayConfig()
    missing = [
        group
        for group, spec in GROUP_SPECS.items()
        if spec["kind"] == "profile" and spec["profile"] not in cfg.llm_ensemble.profiles
    ]

    assert missing == []


def test_draco_runner_profile_groups_exist_when_example_config_is_loaded() -> None:
    cfg = GatewayConfig.load("opensquilla.toml.example")
    missing = [
        group
        for group, spec in GROUP_SPECS.items()
        if spec["kind"] == "profile" and spec["profile"] not in cfg.llm_ensemble.profiles
    ]

    assert missing == []


def test_draco_runner_profile_provider_records_candidates_for_results() -> None:
    cfg = GatewayConfig()
    inherited = ProviderConfig(
        provider="openrouter",
        model="z-ai/glm-5.2",
        api_key="sk-test",
        base_url="https://openrouter.ai/api",
    )

    provider = build_profile_provider(
        config=cfg,
        inherited=inherited,
        group="G3",
        profile="g3_standard",
        dry_run=False,
    )

    assert provider.record_candidates is True


def test_draco_runner_expands_outer_timeout_for_profile_budget() -> None:
    cfg = GatewayConfig()

    assert group_timeout_seconds(requested_timeout=360.0, config=cfg, group="G6") == 450.0
    assert group_timeout_seconds(requested_timeout=600.0, config=cfg, group="G6") == 600.0
    assert group_timeout_seconds(requested_timeout=360.0, config=cfg, group="B2") == 360.0


def test_draco_summary_compares_avg_quality_and_cost_pct_against_baselines() -> None:
    rows = [
        {
            "task_id": "task-1",
            "group": "B0",
            "latency_ms": 100,
            "quality_total": 40.0,
            "judge": {"pass_rate": 40.0, "judge_error_count": 0},
            "usage": {"billed_cost": 0.10, "input_tokens": 10, "output_tokens": 5},
            "error": "",
        },
        {
            "task_id": "task-1",
            "group": "B1",
            "latency_ms": 200,
            "quality_total": 30.0,
            "judge": {"pass_rate": 30.0, "judge_error_count": 0},
            "usage": {"billed_cost": 0.20, "input_tokens": 12, "output_tokens": 6},
            "error": "",
        },
        {
            "task_id": "task-1",
            "group": "G2",
            "latency_ms": 300,
            "quality_total": 45.0,
            "judge": {"pass_rate": 50.0, "judge_error_count": 0},
            "usage": {"billed_cost": 0.05, "input_tokens": 14, "output_tokens": 7},
            "error": "",
        },
    ]

    summary = summarize(rows)
    g2 = summary["groups"]["G2"]

    assert g2["avg_quality_pct_delta_vs_b0"] == pytest.approx(12.5)
    assert g2["avg_cost_pct_delta_vs_b0"] == pytest.approx(-50.0)
    assert g2["avg_quality_pct_delta_vs_b1"] == pytest.approx(50.0)
    assert g2["avg_cost_pct_delta_vs_b1"] == pytest.approx(-75.0)
    markdown = render_markdown(summary, Path("reports/draco/draco_ensemble_test.jsonl"))
    assert "Win vs" not in markdown
    assert "AvgQ % vs B0" in markdown
    assert "+12.50%" in markdown
    assert "-50.00%" in markdown


def test_load_tasks_accepts_official_draco_problem_and_answer(tmp_path: Path) -> None:
    input_path = tmp_path / "draco.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "task_id": "task-1",
                "problem": "Research this.",
                "answer": json.dumps(
                    {
                        "id": "rubric-1",
                        "sections": [
                            {
                                "id": "factual-accuracy",
                                "title": "Factual Accuracy",
                                "criteria": [
                                    {
                                        "id": "fact-1",
                                        "weight": 10,
                                        "requirement": "States the key fact",
                                    }
                                ],
                            }
                        ],
                    }
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    [task] = load_tasks(input_path)

    assert task["id"] == "task-1"
    assert task["prompt"] == "Research this."
    assert task["rubric"]["sections"][0]["criteria"][0]["id"] == "fact-1"


@pytest.mark.asyncio
async def test_judge_text_uses_draco_criterion_judgments() -> None:
    task = {
        "id": "task-1",
        "prompt": "Research this.",
        "rubric": {
            "id": "rubric-1",
            "sections": [
                {
                    "id": "factual-accuracy",
                    "title": "Factual Accuracy",
                    "criteria": [
                        {"id": "pos", "weight": 10, "requirement": "Contains fact"},
                        {"id": "neg", "weight": -5, "requirement": "Contains error"},
                    ],
                }
            ],
        },
    }

    result = await judge_text(
        judge_provider=_CriterionJudgeProvider(),
        task=task,
        answer="A researched answer.",
        dry_run=False,
    )

    assert result is not None
    assert result["mode"] == "draco_criterion_judgments"
    assert result["normalized_score"] == 100.0
    assert result["pass_rate"] == 100.0
    assert result["criteria_count"] == 2
    assert [item["verdict"] for item in result["criterion_judgments"]] == ["MET", "UNMET"]


def test_invalid_criterion_judgment_marks_score_partial() -> None:
    result = score_criterion_judgments(
        rubric_id="rubric-1",
        judge_model="judge-test",
        judge_repeats=1,
        judgments=[
            {"id": "pos", "weight": 10, "met": True},
            {
                "id": "neg",
                "weight": -5,
                "met": None,
                "error": "judge_verdict_parse_failed",
            },
        ],
    )

    assert result["score_status"] == "partial"
    assert result["invalid_criteria_count"] == 1
    assert result["pass_rate"] is None
    assert result["total"] is None
    assert result["valid_pass_rate"] == 100.0
    assert quality_total(result) is None


def test_quality_total_normalizes_legacy_dimension_scores() -> None:
    assert quality_total({"mode": "legacy_dimension_score", "total": 20}) == 100.0
    assert quality_total({"mode": "legacy_dimension_score", "total": 10}) == 50.0
    assert (
        quality_total(
            {
                "mode": "legacy_dimension_score",
                "scores": {
                    "accuracy": 5,
                    "completeness": 4,
                    "objectivity": 3,
                    "citation": 2,
                },
            }
        )
        == 70.0
    )


@pytest.mark.asyncio
async def test_collect_run_enforces_outer_timeout() -> None:
    result = await collect_run(
        _SlowProvider(),
        "slow task",
        timeout=0.01,
    )

    assert result.final_text == ""
    assert "TimeoutError" in result.error
    assert result.trace_events[-1]["kind"] == "timeout"
