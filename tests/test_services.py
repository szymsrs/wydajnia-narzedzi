import unittest
import importlib

issue = importlib.import_module('app.domain.services.issue')
return_service = importlib.import_module('app.domain.services.return')
scrap = importlib.import_module('app.domain.services.scrap')
inventory = importlib.import_module('app.domain.services.inventory')
rw = importlib.import_module('app.domain.services.rw')


class FakeCursor:
    def __init__(self, log):
        self.log = log

    def callproc(self, name, args):
        self.log.append((name, args))


class FakeDB:
    def __init__(self):
        self.log = []
        self.commit_count = 0

    def cursor(self):
        return FakeCursor(self.log)

    def commit(self):
        self.commit_count += 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass


class ServiceTests(unittest.TestCase):
    def setUp(self):
        issue._processed_ops.clear()
        return_service._processed_ops.clear()
        scrap._processed_ops.clear()
        inventory._processed_ops.clear()
        rw._processed_ops.clear()
        self.db = FakeDB()

    def _test_service(self, func, base_args, proc_name, expected_args):
        # RFID not confirmed
        res = func(self.db, *base_args, operation_uuid='op1', rfid_confirmed=False)
        self.assertEqual(res['status'], 'rfid_unconfirmed')
        self.assertEqual(self.db.log, [])
        self.assertEqual(self.db.commit_count, 0)

        # Success
        res = func(self.db, *base_args, operation_uuid='op1', rfid_confirmed=True)
        self.assertEqual(res['status'], 'success')
        self.assertEqual(self.db.log, [(proc_name, expected_args)])
        self.assertEqual(self.db.commit_count, 1)

        # Duplicate
        res = func(self.db, *base_args, operation_uuid='op1', rfid_confirmed=True)
        self.assertEqual(res['status'], 'duplicate')
        self.assertEqual(self.db.log, [(proc_name, expected_args)])
        self.assertEqual(self.db.commit_count, 1)

    def test_issue(self):
        self._test_service(issue.issue_tool, (1, 2, 3), 'sp_issue_tool', (1, 2, '3', 'op1'))

    def test_return(self):
        self._test_service(return_service.return_tool, (1, 2, 3), 'sp_return_tool', (1, 2, '3', 'op1'))

    def test_scrap(self):
        self._test_service(scrap.scrap_tool, (1, 2, 3), 'sp_scrap_tool', (1, 2, '3', None, 'op1'))

    def test_inventory(self):
        self._test_service(inventory.inventory_count, (2, 3), 'sp_inventory_count', (2, '3', 'op1'))

    def test_rw(self):
        self._test_service(rw.record_rw_receipt, (10, 2, 3), 'sp_rw_receipt', (10, 2, '3', 'op1'))


if __name__ == '__main__':
    unittest.main()
