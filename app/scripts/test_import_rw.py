# scripts/test_import_rw.py
from __future__ import annotations
import sys, json

# Podmień na właściwy import Twojego repo
# from app.dal.repo import Repo
class DummyRepo:
    """Przykładowy adapter do testu. Zastąp własnym repo!"""
    def __init__(self):
        # Minimalne dane do testu
        self._users = [
            {"id": 1, "first_name": "Adam", "last_name": "Admin", "login": "admin", "active": 1},
            {"id": 2, "first_name": "Jan",  "last_name": "Rychlik", "login": "jr", "active": 1},
            {"id": 3, "first_name": "Szymon","last_name": "Sierszulski","login":"ss", "active": 1},
        ]
        self._items = {
            "0 641 210 023 0O": 101,
            "0 273 003 017 -057": 102,
        }
    def list_employees(self, q):
        q = (q or "").lower()
        return [u for u in self._users if q in u["last_name"].lower() or q in u["first_name"].lower()]
    def get_item_id_by_sku(self, sku):
        return self._items.get(sku)
    def find_item_by_name(self, name):
        return None  # tu można dorobić fuzzy
    def create_operation(self, **kwargs):
        print("CREATE OPERATION:", json.dumps(kwargs, ensure_ascii=False, indent=2))
        return "uuid-demo-1234"

def main():
    if len(sys.argv) < 2:
        print("Użycie: python scripts/test_import_rw.py /ścieżka/do/RW.pdf")
        sys.exit(1)
    pdf_path = sys.argv[1]

    from app.services.rw.importer import import_rw_pdf

    repo = DummyRepo()  # ZAMIENIĆ na Repo(...)
    res = import_rw_pdf(repo, pdf_path, operator_user_id=1, station="ST-01", commit=False)  # dry-run
    if res.get("ok") and not res.get("dry_run"):
        print("OK, utworzono operację:", res["op_uuid"])
    elif res.get("ok") and res.get("dry_run"):
        print("DRY RUN – podgląd:")
        print(json.dumps(res["preview"], ensure_ascii=False, indent=2))
    else:
        print("Potrzebne uzupełnienia:")
        print(json.dumps(res["need"], ensure_ascii=False, indent=2))
        print("RW:", res.get("rw"))

if __name__ == "__main__":
    main()
