#!/usr/bin/env python3
"""
Unit tests for render_plan.py.

Run directly:
    python3 -m unittest project-epic-planner/scripts/test_render_plan.py
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import render_plan  # noqa: E402

LABELS = {"epic", "task", "priority:P0", "size:S"}
PR_AGENT_PLAN = (Path(__file__).parent.parent.parent / "github-project-bootstrap"
                 / "docs" / "pr-agent-tracker.json")


def _plan() -> dict:
    return {
        "milestone": {"title": "v1", "description": "Ship it."},
        "epics": [
            {"title": "Epic: A", "labels": ["priority:P0"], "body": "A body.",
             "issues": [{"title": "Story A1", "labels": ["size:S"], "body": "A1 body."}]},
            {"title": "Epic: B", "depends_on": ["Epic: A"], "body": "B body.",
             "issues": [{"title": "Story B1", "body": "B1 body."}]},
        ],
        "release_validation_issue": {"title": "RV", "labels": [], "body": "RV."},
    }


def _run_main(plan: dict, *extra_args: str) -> tuple[int, str, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(plan, f)
    out, err = io.StringIO(), io.StringIO()
    argv = ["render_plan.py", "--data", f.name, *extra_args]
    code = 0
    with mock.patch.object(sys, "argv", argv), \
         contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            render_plan.main()
        except SystemExit as exc:
            code = exc.code or 0
    return code, out.getvalue(), err.getvalue()


class CheckPlanTests(unittest.TestCase):
    def test_valid_plan_has_no_problems(self) -> None:
        self.assertEqual(render_plan.check_plan(_plan(), LABELS), [])

    def test_duplicate_title_across_epics_is_reported(self) -> None:
        plan = _plan()
        plan["epics"][1]["issues"][0]["title"] = "Story A1"
        problems = render_plan.check_plan(plan, LABELS)
        self.assertEqual(len(problems), 1)
        self.assertIn("duplicate issue title (2x): 'Story A1'", problems[0])

    def test_duplicate_of_release_validation_title_is_reported(self) -> None:
        plan = _plan()
        plan["release_validation_issue"]["title"] = "Epic: B"
        self.assertIn("'Epic: B'", render_plan.check_plan(plan, LABELS)[0])

    def test_unknown_label_is_reported_with_issue_title(self) -> None:
        plan = _plan()
        plan["epics"][0]["issues"][0]["labels"] = ["size:XL"]
        problems = render_plan.check_plan(plan, LABELS)
        self.assertEqual(problems, ["'Story A1' uses label(s) not in the labels file: size:XL"])

    def test_labels_file_missing_implicit_epic_and_task_is_reported(self) -> None:
        problems = render_plan.check_plan(_plan(), LABELS - {"epic", "task"})
        self.assertIn("'Epic: A' uses label(s) not in the labels file: epic", problems)
        self.assertIn("'Story B1' uses label(s) not in the labels file: task", problems)
        self.assertFalse(any("'RV'" in p for p in problems))

    def test_non_string_label_and_title_are_reported_not_raised(self) -> None:
        plan = _plan()
        plan["epics"][0]["issues"][0]["labels"] = [None]
        plan["epics"][1]["title"] = ["not", "a", "string"]
        self.assertEqual(render_plan.check_plan(plan, LABELS), [
            "'Story A1' labels must all be strings: [None]",
            "title must be a string, got ['not', 'a', 'string']",
        ])


class RenderTests(unittest.TestCase):
    def test_render_includes_counts_graph_and_every_title(self) -> None:
        md = render_plan.render(_plan())
        self.assertIn("2 epics, 2 stories, 1 release-validation issue — 5 issues in total.", md)
        self.assertIn("| 2 | Epic: B | Epic: A | 1 |", md)
        for title in ("## 1. Epic: A", "#### 1.1 Story A1", "## 2. Epic: B",
                      "#### 2.1 Story B1", "## Release validation: RV"):
            self.assertIn(title, md)

    def test_pipe_in_title_is_escaped_in_dependency_table(self) -> None:
        plan = _plan()
        plan["epics"][0]["title"] = "Epic: CLI | API"
        plan["epics"][1]["depends_on"] = ["Epic: CLI | API"]
        md = render_plan.render(plan)
        self.assertIn("| 1 | Epic: CLI \\| API | — | 1 |", md)
        self.assertIn("| 2 | Epic: B | Epic: CLI \\| API | 1 |", md)

    def test_story_body_headings_nest_below_story_heading(self) -> None:
        plan = _plan()
        plan["epics"][0]["issues"][0]["body"] = "## What\nDo it.\n\n## Acceptance criteria\n- [ ] x"
        md = render_plan.render(plan)
        self.assertIn("\n##### What\n", md)
        self.assertIn("\n##### Acceptance criteria\n", md)
        self.assertNotIn("\n## What\n", md)

    def test_epic_and_rv_body_headings_nest_below_level_two(self) -> None:
        plan = _plan()
        plan["epics"][0]["body"] = "# Goal\ntext\n## Detail\nmore"
        plan["release_validation_issue"]["body"] = "## Checks\n1. run it"
        md = render_plan.render(plan)
        self.assertIn("\n### Goal\n", md)
        self.assertIn("\n#### Detail\n", md)
        self.assertIn("\n### Checks\n", md)

    def test_already_deep_headings_are_left_alone(self) -> None:
        body = "text\n\n###### Deep\n"
        self.assertEqual(render_plan._nest(body, 4), body)

    def test_hash_lines_inside_code_fences_are_not_headings(self) -> None:
        body = ("## What\n```ruby\n# a comment\n## not a heading\n```\n"
                "~~~bash\n# shell comment\n~~~\n## Acceptance criteria")
        nested = render_plan._nest(body, 4)
        self.assertIn("\n# a comment\n## not a heading\n", nested)
        self.assertIn("\n# shell comment\n", nested)
        self.assertTrue(nested.startswith("##### What\n"))
        self.assertTrue(nested.endswith("\n##### Acceptance criteria"))

    def test_fence_line_with_info_string_does_not_close_open_fence(self) -> None:
        body = "## What\n```\nexample:\n```ruby\n```\n## AC"
        self.assertEqual(render_plan._nest(body, 4),
                         "##### What\n```\nexample:\n```ruby\n```\n##### AC")

    def test_stories_sit_under_their_own_section_not_the_epic_bodys_last_heading(self) -> None:
        plan = _plan()
        plan["epics"][0]["body"] = "## Goal\ntext\n## Unblocks\nmore"
        md = render_plan.render(plan)
        unblocks = md.index("### Unblocks")
        stories = md.index("### Stories in this epic (1)")
        story = md.index("#### 1.1 Story A1")
        self.assertLess(unblocks, stories)
        self.assertLess(stories, story)

    def test_heading_levels_cap_at_six(self) -> None:
        self.assertEqual(render_plan._nest("# A\n### B", 4), "##### A\n###### B")

    def test_rv_title_already_prefixed_is_not_doubled(self) -> None:
        plan = _plan()
        plan["release_validation_issue"]["title"] = "Release validation: full run"
        md = render_plan.render(plan)
        self.assertIn("\n## Release validation: full run\n", md)
        self.assertNotIn("Release validation: Release validation", md)

    def test_render_shows_implicit_epic_and_task_labels(self) -> None:
        md = render_plan.render(_plan())
        self.assertIn("**Labels:** `epic`, `priority:P0`", md)
        self.assertIn("**Labels:** `task`, `size:S`", md)
        self.assertIn("**Labels:** `task`\n", md)


class MainTests(unittest.TestCase):
    def test_valid_plan_writes_markdown_to_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "plan.md"
            code, stdout, _ = _run_main(_plan(), "--out", str(out_path))
            self.assertEqual(code, 0)
            self.assertIn("Wrote", stdout)
            self.assertIn("## 1. Epic: A", out_path.read_text())

    def test_forward_depends_on_fails_via_bootstrap_loader(self) -> None:
        plan = _plan()
        plan["epics"][0]["depends_on"] = ["Epic: B"]
        code, stdout, stderr = _run_main(plan)
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("not defined earlier", stderr)

    def test_unknown_label_fails_and_writes_nothing(self) -> None:
        plan = _plan()
        plan["epics"][0]["labels"] = ["nope"]
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "plan.md"
            code, _, stderr = _run_main(plan, "--out", str(out_path))
            self.assertEqual(code, 1)
            self.assertIn("nope", stderr)
            self.assertFalse(out_path.exists())

    def test_real_pr_agent_plan_validates_against_default_labels(self) -> None:
        code, stdout, stderr = _run_main(json.loads(PR_AGENT_PLAN.read_text()))
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("8 epics, 42 stories, 1 release-validation issue — 51 issues in total.", stdout)


if __name__ == "__main__":
    unittest.main()
