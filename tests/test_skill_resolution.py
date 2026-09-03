from __future__ import annotations

import unittest
from pathlib import Path

from src.planbot import crew_workflow


class TestResolveAgentSkills(unittest.TestCase):
    """Unit tests for ``_resolve_agent_skills`` in crew_workflow."""

    def test_resolves_relative_skill_paths(self):
        """Normal flow: a root-relative skill directory resolves to an absolute path."""
        root_dir = Path("/repo")
        agent_def = {"skills": ["data/planbot/shared/common_skills"]}

        resolved = crew_workflow._resolve_agent_skills(agent_def, root_dir)

        self.assertEqual(resolved, [Path("/repo/data/planbot/shared/common_skills")])

    def test_no_skills_returns_empty(self):
        """An agent with no ``skills:`` key resolves to an empty list."""
        self.assertEqual(
            crew_workflow._resolve_agent_skills({}, Path("/repo")),
            [],
        )

    def test_keeps_absolute_skill_paths(self):
        """Already-absolute skill paths are returned unchanged."""
        root_dir = Path("/repo")
        agent_def = {"skills": ["/abs/common_skills"]}

        resolved = crew_workflow._resolve_agent_skills(agent_def, root_dir)

        self.assertEqual(resolved, [Path("/abs/common_skills")])

    def test_non_list_skills_raises(self):
        """Exception flow: a non-list ``skills:`` value raises ValueError."""
        agent_def = {"skills": "data/planbot/shared/common_skills"}

        with self.assertRaises(ValueError):
            crew_workflow._resolve_agent_skills(agent_def, Path("/repo"))


if __name__ == "__main__":
    unittest.main()
