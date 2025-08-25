import unittest

from app.repo.items_repo import ItemsRepo

class FakeResult:
    def mappings(self):
        return self

    def all(self):
        return []

    def scalar_one_or_none(self):
        return None


class FakeConnection:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=None):
        self.log.append((str(sql), params))
        return FakeResult()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass


class FakeEngine:
    def __init__(self):
        self.log = []
        self.conn = FakeConnection(self.log)

    def connect(self):
        return self.conn


class ItemsRepoTests(unittest.TestCase):
    def setUp(self):
        self.engine = FakeEngine()
        self.repo = ItemsRepo(self.engine)

    def test_find_items_query(self):
        self.repo.find_items("ABC")
        sql, params = self.engine.log[-1]
        lower = sql.lower()
        self.assertRegex(lower, r"sku\s+like")
        self.assertRegex(lower, r"name\s+like")
        self.assertEqual(params["q"], "ABC")

    def test_get_item_id_by_sku_query(self):
        self.repo.get_item_id_by_sku("X1")
        sql, params = self.engine.log[-1]
        self.assertRegex(sql.lower(), r"where\s+sku\s*=\s*:sku")
        self.assertEqual(params["sku"], "X1")


if __name__ == "__main__":
    unittest.main()