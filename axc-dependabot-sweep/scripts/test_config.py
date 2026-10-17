#!/usr/bin/env python3
"""
Unit tests for config.py.

Run directly:
    python3 -m unittest axc-dependabot-sweep/scripts/test_config.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402


class ValidateTests(unittest.TestCase):
    def test_fills_defaults(self) -> None:
        resolved = config.validate({"verify": "make test"})
        self.assertEqual(resolved["authors"], ["app/dependabot"])
        self.assertIsNone(resolved["merge_method"])
        self.assertEqual(resolved["timeouts"], {"rebase_minutes": 15, "ci_minutes": 20})
        self.assertEqual(resolved["review_level"], "medium")

    def test_partial_timeouts_keep_the_other_default(self) -> None:
        resolved = config.validate({"verify": "x", "timeouts": {"ci_minutes": 5}})
        self.assertEqual(resolved["timeouts"], {"rebase_minutes": 15, "ci_minutes": 5})

    def test_does_not_mutate_defaults(self) -> None:
        config.validate({"verify": "x", "timeouts": {"ci_minutes": 5}})
        self.assertEqual(config.DEFAULTS["timeouts"]["ci_minutes"], 20)

    def test_verify_required_unless_proposing(self) -> None:
        with self.assertRaises(config.ConfigError):
            config.validate({})
        self.assertIsNone(config.validate({}, require_verify=False)["verify"])

    def test_rejects_bad_values(self) -> None:
        bad = [
            {"verify": ""},
            {"verify": 3},
            {"verify": "x", "authors": []},
            {"verify": "x", "authors": ["ok", ""]},
            {"verify": "x", "authors": "app/dependabot"},
            {"verify": "x", "merge_method": "fast-forward"},
            {"verify": "x", "review_level": "extreme"},
            {"verify": "x", "timeouts": {"ci_minutes": 0}},
            {"verify": "x", "timeouts": {"ci_minutes": True}},
            {"verify": "x", "timeouts": {"nope": 1}},
            {"verify": "x", "timeouts": 5},
            {"verify": "x", "surprise": 1},
        ]
        for case in bad:
            with self.subTest(case=case), self.assertRaises(config.ConfigError):
                config.validate(case)

    def test_accepts_each_merge_method(self) -> None:
        for method in config.MERGE_METHODS:
            self.assertEqual(config.validate({"verify": "x", "merge_method": method})["merge_method"],
                             method)


class RepoTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)

    def touch(self, name: str, content: str = "") -> None:
        (self.repo / name).write_text(content)


class LoadConfigTests(RepoTestCase):
    def test_loads_and_validates_file(self) -> None:
        (self.repo / ".claude").mkdir()
        (self.repo / config.CONFIG_PATH).write_text(json.dumps({"verify": "make test"}))
        self.assertEqual(config.load_config(self.repo)["verify"], "make test")

    def test_invalid_json_is_a_config_error(self) -> None:
        (self.repo / ".claude").mkdir()
        (self.repo / config.CONFIG_PATH).write_text("{nope")
        with self.assertRaises(config.ConfigError):
            config.load_config(self.repo)


class DetectionTests(RepoTestCase):
    def test_detects_from_lockfiles(self) -> None:
        self.touch("yarn.lock")
        self.touch("Gemfile.lock")
        self.assertEqual(config.detect_package_managers(self.repo), ["yarn", "bundler"])

    def test_nothing_detected(self) -> None:
        self.assertEqual(config.detect_package_managers(self.repo), [])
        self.assertIsNone(config.propose_config(self.repo)["verify"])

    def test_yarn_uses_npx_when_yarn_not_on_path(self) -> None:
        self.touch("yarn.lock")
        self.touch("package.json", json.dumps({"scripts": {"esbuild": "x", "build": "y"}}))
        with mock.patch("config.shutil.which", return_value=None):
            verify = config.propose_config(self.repo)["verify"]
        self.assertEqual(verify, "npx -y yarn@1 install --frozen-lockfile && "
                                 "npx -y yarn@1 run build")

    def test_yarn_on_path(self) -> None:
        self.touch("yarn.lock")
        with mock.patch("config.shutil.which", return_value="/usr/bin/yarn"):
            verify = config.propose_config(self.repo)["verify"]
        self.assertEqual(verify, "yarn install --frozen-lockfile")

    def test_npm_includes_build_and_test_scripts_when_present(self) -> None:
        self.touch("package-lock.json")
        self.touch("package.json", json.dumps({"scripts": {"test": "t", "build": "b"}}))
        self.assertEqual(config.propose_config(self.repo)["verify"],
                         "npm ci && npm run build && npm run test")

    def test_malformed_package_json_is_ignored(self) -> None:
        self.touch("package-lock.json")
        self.touch("package.json", "{nope")
        self.assertEqual(config.propose_config(self.repo)["verify"], "npm ci")

    def test_multiple_managers_chain_with_and(self) -> None:
        self.touch("package-lock.json")
        self.touch("Gemfile.lock")
        self.assertEqual(config.propose_config(self.repo)["verify"], "npm ci && bundle install")

    def test_proposal_is_valid(self) -> None:
        self.touch("uv.lock")
        config.validate(config.propose_config(self.repo))


if __name__ == "__main__":
    unittest.main()
