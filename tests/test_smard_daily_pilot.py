import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pilot.smard_daily_pilot import (
    FILTER_LOAD, FILTER_RENEWABLES, PilotUnavailable, daily_hours_utc, build_preview,
)

LOCAL = ZoneInfo('Europe/Berlin')


def fake_source(day, missing=None, future_extra=False):
    hours = daily_hours_utc(day)
    package = int((hours[0] - timedelta(days=2)).timestamp() * 1000)
    forecasts = {
        FILTER_LOAD: [[int(h.timestamp() * 1000), 50000 + i] for i, h in enumerate(hours)],
        FILTER_RENEWABLES: [[int(h.timestamp() * 1000), 15000 + i] for i, h in enumerate(hours)],
    }
    if missing is not None:
        forecasts[FILTER_RENEWABLES].pop(missing)
    if future_extra:
        forecasts[FILTER_LOAD].append([
            int((hours[-1] + timedelta(hours=1)).timestamp() * 1000), 60000
        ])

    def fetch(path):
        if path.startswith('https://'):
            raise AssertionError('expected path-only injectable stub')
        for fid in (FILTER_LOAD, FILTER_RENEWABLES):
            if path == f'/{fid}/DE/index_hour.json':
                return {'timestamps': [package]}
            if path == f'/{fid}/DE/{fid}_DE_hour_{package}.json':
                return {'series': forecasts[fid], 'meta_data': {'version': 1}}
        raise AssertionError(f'unexpected URL path {path}')
    return fetch


class PilotTests(unittest.TestCase):
    def test_ordinary_day_is_24_hours(self):
        hours = daily_hours_utc(date(2026, 11, 21))
        self.assertEqual(len(hours), 24)
        self.assertEqual(len(set(hours)), 24)

    def test_dst_spring_and_autumn_use_physical_utc_hours(self):
        self.assertEqual(len(daily_hours_utc(date(2027, 3, 28))), 23)
        self.assertEqual(len(daily_hours_utc(date(2027, 10, 31))), 25)

    def test_snapshot_is_preview_not_certified_live_model(self):
        now = datetime(2026, 11, 20, 18, 45, tzinfo=LOCAL)
        result = build_preview(date(2026, 11, 21), now, fake_source(date(2026, 11, 21)))
        self.assertEqual(result['status'], 'RESEARCH_PREVIEW_ONLY')
        self.assertEqual(result['model_inference'], 'NOT_AVAILABLE')
        self.assertIsNone(result['ensemble_forecast'])
        self.assertEqual(result['source_vintage_verified'], False)
        self.assertEqual(len(result['hours']), 24)
        self.assertEqual(result['hours'][0]['smard_component_residual_mwh'], 35000.0)
        self.assertEqual(result['dataset'], 'Bundesnetzagentur | SMARD.de')
        self.assertTrue(all(row['smard_component_residual_mwh'] == 35000.0 for row in result['hours']))

    def test_before_publication_cutoff_fails_closed(self):
        now = datetime(2026, 11, 20, 17, 59, tzinfo=LOCAL)
        with self.assertRaisesRegex(PilotUnavailable, '18:15'):
            build_preview(date(2026, 11, 21), now, fake_source(date(2026, 11, 21)))

    def test_wrong_delivery_date_fails_closed(self):
        now = datetime(2026, 11, 20, 19, 0, tzinfo=LOCAL)
        with self.assertRaisesRegex(PilotUnavailable, 'tomorrow'):
            build_preview(date(2026, 11, 22), now, fake_source(date(2026, 11, 22)))

    def test_missing_hour_fails_closed(self):
        now = datetime(2026, 11, 20, 19, 0, tzinfo=LOCAL)
        with self.assertRaisesRegex(PilotUnavailable, 'missing'):
            build_preview(date(2026, 11, 21), now, fake_source(date(2026, 11, 21), missing=5))

    def test_future_hour_outside_day_is_ignored_not_silent_fallback(self):
        now = datetime(2026, 11, 20, 19, 0, tzinfo=LOCAL)
        result = build_preview(date(2026, 11, 21), now, fake_source(date(2026, 11, 21), future_extra=True))
        self.assertEqual(len(result['hours']), 24)

    def test_negative_load_is_rejected(self):
        day = date(2026, 11, 21)
        def corrupted(path):
            ans = fake_source(day)(path)
            if path.startswith('/411/DE/411_'):
                ans['series'][0][1] = -3
            return ans
        with self.assertRaisesRegex(PilotUnavailable, 'invalid'):
            build_preview(day, datetime(2026, 11, 20, 19, tzinfo=LOCAL), corrupted)

    def test_no_model_or_hidden_fallback_from_saved_joblib(self):
        import inspect
        from pilot import smard_daily_pilot
        src = inspect.getsource(smard_daily_pilot)
        self.assertNotIn('joblib.load', src)
        self.assertNotIn('pickle.load', src)
        self.assertNotIn('ensemble_predict(', src)


if __name__ == '__main__':
    unittest.main()
