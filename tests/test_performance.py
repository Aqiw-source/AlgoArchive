import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app
from app import Repository


class RepositoryPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="algo-performance-")
        self.addCleanup(self.tmp.cleanup)
        self.repo = Repository(Path(self.tmp.name) / "data")
        self.addCleanup(self.repo.close)

    def create_algorithms(self, count):
        for index in range(count):
            self.repo.create_algorithm(
                {
                    "name": f"Algorithm {index}",
                    "category": "Performance",
                    "description": "",
                    "links": [],
                }
            )

    def state_query_count(self):
        statements = []
        self.repo.db.set_trace_callback(statements.append)
        try:
            state = self.repo.state()
        finally:
            self.repo.db.set_trace_callback(None)
        return state, len(statements)

    def test_state_query_count_does_not_grow_with_algorithm_count(self):
        self.create_algorithms(1)
        small_state, small_query_count = self.state_query_count()

        self.create_algorithms(12)
        large_state, large_query_count = self.state_query_count()

        self.assertEqual(1, len(small_state["algorithms"]))
        self.assertEqual(13, len(large_state["algorithms"]))
        self.assertEqual(small_query_count, large_query_count)

    def test_code_only_save_skips_platform_order_reconciliation(self):
        problem = self.repo.create_problem({
            "platform": "Codeforces", "name": "A", "url": "https://example.com/A",
            "language": "cpp", "code": "",
        })
        with mock.patch.object(self.repo, "_sync_platform_orders",
                               wraps=self.repo._sync_platform_orders) as reconcile:
            self.repo.update_problem(problem["id"], {"version": problem["version"], "code": "int main() {}"})
            reconcile.assert_not_called()

    def test_platform_statistics_normalize_each_problem_once(self):
        values = ['codeforces', 'Codeforces', 'AtCoder', 'acwing', 'luogu', '洛谷', 'nowcoder', 'CustomJudge']
        for index, platform in enumerate(values):
            self.repo.create_problem({'platform': platform, 'name': str(index),
                                     'url': 'https://example.com/' + str(index),
                                     'language': 'cpp', 'code': ''})
        with mock.patch('app.platform_identity', wraps=app.platform_identity) as normalize:
            stats = self.repo.state()['stats']
        self.assertEqual([stats[key + '_count'] for key in ('codeforces', 'atcoder', 'acwing', 'luogu', 'niuke')], [2, 1, 1, 2, 1])
        self.assertEqual(stats['problem_count'], 8)
        self.assertLessEqual(normalize.call_count, len(values) + 5)


if __name__ == "__main__":
    unittest.main()
