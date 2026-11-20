"""Offline regression checks for isolated Streamlit pilot and original team credit."""

import ast
from pathlib import Path
import unittest

from pilot.team_credits import (
    ORIGINAL_TEAM_MEMBERS,
    ORIGINAL_TEAM_REPOSITORY,
    PERSONAL_RESEARCH_FORK,
)

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "pilot/smard_streamlit.py"
ORIGINAL_ABOUT = ROOT / "streamlit/app_pages/about.py"


class StreamlitContractTests(unittest.TestCase):
    def test_all_four_human_team_members_match_original_team_app(self):
        source = ast.parse(ORIGINAL_ABOUT.read_text(encoding="utf-8"))
        team_node = next(
            stmt.value
            for stmt in source.body
            if isinstance(stmt, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "TEAM"
                    for target in stmt.targets)
        )
        original_humans = tuple(entry[0] for entry in ast.literal_eval(team_node)[:4])
        self.assertEqual(original_humans, ORIGINAL_TEAM_MEMBERS)
        self.assertEqual(set(original_humans), {"Robert", "Marco", "Hari", "Monica"})

    def test_streamlit_bootstrap_precedes_pilot_imports(self):
        source = APP.read_text(encoding="utf-8")
        self.assertLess(
            source.index("sys.path.insert(0, str(_REPO_ROOT))"),
            source.index("from pilot.smard_daily_pilot import"),
        )
        self.assertIn("Path(__file__).resolve().parents[1]", source)
        compile(source, str(APP), "exec")

    def test_prominent_credit_and_independent_pilot_boundary(self):
        source = APP.read_text(encoding="utf-8")
        self.assertLess(source.index("ORIGINAL_TEAM_MEMBERS)"), source.index("st.warning("))
        self.assertIn("does not imply the other members developed or endorsed it", source)
        self.assertIn("ORIGINAL_TEAM_REPOSITORY", source)
        self.assertIn("PERSONAL_RESEARCH_FORK", source)
        self.assertEqual(ORIGINAL_TEAM_REPOSITORY, "https://github.com/fruchtgummikauer/grid-stress")
        self.assertEqual(PERSONAL_RESEARCH_FORK, "https://github.com/harirsingh25-source/grid-stress")


if __name__ == "__main__":
    unittest.main()
