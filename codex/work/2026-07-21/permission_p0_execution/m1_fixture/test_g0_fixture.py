import unittest

from g0_fixture import REQUIRED_EVENT_FIELDS, TARGET, assert_contract, run_all, run_case


class G0FixtureTest(unittest.TestCase):
    def test_all_six_cases_satisfy_contract(self) -> None:
        assert_contract(run_all())

    def test_in_filter_stale_grant_is_not_recoverable(self) -> None:
        fresh = run_case("IN_FILTER", "fresh")
        stale = run_case("IN_FILTER", "stale")

        self.assertEqual(fresh["returned_node"], TARGET)
        self.assertNotEqual(stale["returned_node"], TARGET)
        self.assertIn("bridge_rejected", stale["target_node_event_sequence"])
        self.assertNotIn("main_pool_read", stale["target_node_event_sequence"])
        self.assertNotIn("exact_allow", stale["target_node_event_sequence"])

    def test_pre_filter_stale_materialization_omits_target(self) -> None:
        fresh = run_case("PRE_FILTER", "fresh")
        stale = run_case("PRE_FILTER", "stale")

        self.assertEqual(fresh["returned_node"], TARGET)
        self.assertNotEqual(stale["returned_node"], TARGET)
        self.assertIn("pre_filter_omit", stale["target_node_event_sequence"])
        self.assertNotIn("main_pool_read", stale["target_node_event_sequence"])

    def test_post_filter_is_freshness_negative_control(self) -> None:
        fresh = run_case("POST_FILTER", "fresh")
        stale = run_case("POST_FILTER", "stale")

        self.assertEqual(fresh["returned_node"], TARGET)
        self.assertEqual(stale["returned_node"], TARGET)
        fresh.pop("approximate_state")
        stale.pop("approximate_state")
        self.assertEqual(fresh, stale)

    def test_required_counters_are_explicit_and_io_accounting_closes(self) -> None:
        for case in run_all():
            for field in REQUIRED_EVENT_FIELDS:
                self.assertIn(field, case)
                self.assertIsInstance(case[field], int)
            self.assertEqual(
                case["main_pool_read"],
                case["backend_cache_hit"] + case["device_submit"],
            )


if __name__ == "__main__":
    unittest.main()
