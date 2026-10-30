import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
