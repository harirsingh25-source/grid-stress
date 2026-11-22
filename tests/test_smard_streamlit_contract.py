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

    def test_tomorrow_view_uses_only_guarded_preflight_after_1815(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn("Tomorrow's SMARD input preview", source)
        self.assertIn("local_now.time() < time(18, 15)", source)
        self.assertIn("build_preview(next_day, datetime.now(timezone.utc))", source)
        self.assertIn("st.button(\"Fetch tomorrow's SMARD input snapshot\"", source)
        self.assertLess(
            source.index('if not st.button("Fetch tomorrow'),
            source.index("build_preview(next_day"),
        )
        self.assertIn("source_vintage_verified", source)
        self.assertIn("public_release_authorized", source)
        self.assertIn('preview.get("model_inference") != "NOT_AVAILABLE"', source)
        self.assertIn('preview.get("ensemble_forecast") is not None', source)

    def test_original_historical_view_kept_and_pilot_does_not_schedule(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn('st.button("Fetch SMARD historical inputs"', source)
        self.assertIn("build_historical_snapshot(", source)
        self.assertIn("HISTORICAL_COMPONENT_PREVIEW_ONLY", (
            ROOT / "pilot/smard_historical_snapshot.py"
        ).read_text(encoding="utf-8"))
        self.assertNotIn("st_autorefresh", source)
        self.assertNotIn("scheduler.add_job", source)

    def test_tomorrow_ui_discloses_ridge_missing_features_without_fake_model(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn("from pilot.ridge_readiness import readiness_report", source)
        self.assertIn("ridge = readiness_report(preview)", source)
        self.assertIn("Inspect the seven missing Ridge-model inputs", source)
        self.assertIn('pd.DataFrame(ridge["unavailable_features"])', source)
        self.assertIn('metric_ensemble.metric("GridStress ensemble", "Not available")', source)
        self.assertIn("A trained Ridge", source)
        self.assertIn('" · ".join(ORIGINAL_TEAM_MEMBERS)', source)


if __name__ == "__main__":
    unittest.main()
