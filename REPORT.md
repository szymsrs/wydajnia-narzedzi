# AUDYT: RW → SQL → Stan → Wydanie → Zwrot (Wydajnia Narzędzi)

Autor: Codex CLI audit
Data: auto z repo lokalnego

## A. Mapa przepływu RW → SQL

- Źródło/GUI: `app/ui/rw_import_dialog.py`
  - Parsowanie PDF: `parse_rw_pdf(path, debug_path)` (app/services/rw/parser.py)
  - Zapis do DB (metody repo, linie wywołań):
    - upsert pozycji: `app/ui/rw_import_dialog.py:125` → `RWImportRepo.upsert_item`
    - nagłówek RW: `app/ui/rw_import_dialog.py:131` → `RWImportRepo.insert_rw_header`
    - linia RW: `app/ui/rw_import_dialog.py:139` → `RWImportRepo.insert_rw_line`
    - commit transakcji: `app/ui/rw_import_dialog.py:157` → `RWImportRepo.commit_transaction`

- Repo importu RW: `app/dal/rw_import_repo.py`
  - Rozpoznanie schematu (wykrywanie kolumn): `__init__` (linie ok. 17–55): `SHOW COLUMNS FROM …`
  - upsert_item:
    - SELECT item po SKU/kodzie: `SELECT id, <name_col> FROM items WHERE <code_col>=:s LIMIT 1`
    - UPDATE nazwy pozycji (gdy jest): `UPDATE items SET <name_col>=:n WHERE id=:id`
    - INSERT pozycji (z unit/uom gdy NOT NULL): `INSERT INTO items(<code_col>,<name_col>[,<unit/uom>]) VALUES (:s,:n[,'SZT'])`
  - insert_rw_header:
    - INSERT dokumentu: `INSERT INTO documents(doc_type, number, doc_date, source_file, parse_confidence {extra}) VALUES (...)`
      - doc_type='RW'; opcjonalne: issued_without_return gdy kolumna istnieje.
  - insert_rw_line:
    - STOCK (źródło: tabela stock, jeśli istnieje):
      - SELECT qty FOR UPDATE: `SELECT <quantity_col> FROM stock WHERE <item_col>=:i FOR UPDATE`
      - INSERT/UPDATE: `INSERT INTO stock(item_id,quantity)` lub `UPDATE stock SET quantity=quantity+:q WHERE item_id=:i`
    - INSERT linii dokumentu: `INSERT INTO document_lines(document_id,item_id,qty[,unit_price_netto,...]) VALUES (...)`
    - INSERT ruchu RECEIPT: `INSERT INTO movements(item_id, qty, from_location_id, to_location_id, movement_type, document_line_id) VALUES (...,'RECEIPT', :dl)`
  - commit_transaction:
    - INSERT do logu transakcji (gdy kolumny istnieją): `INSERT INTO transactions(operation_uuid, movement_type[, employee_id, station, method, created_at]) VALUES (...)`
    - COMMIT i zamknięcie connection.

- Starsza ścieżka (legacy): `app/dal/rw_repo_mysql.py`
  - Przyjęcie z linii dokumentu (SP): `app/dal/rw_repo_mysql.py:113` → `cur.callproc('sp_receipt_from_line', (...))`
    - Zakładamy, że SP księguje: document_lines, lots, movements/movement_allocations.

Dowody (rg):

```
app/dal/rw_import_repo.py:155: SELECT ... FROM stock ... FOR UPDATE
app/dal/rw_import_repo.py:204: INSERT INTO document_lines(...)
app/dal/rw_import_repo.py:216: INSERT INTO movements(... 'RECEIPT' ...)
app/dal/rw_import_repo.py:270: INSERT INTO transactions(...)
app/dal/rw_repo_mysql.py:113: cur.callproc('sp_receipt_from_line', (...))
```

## B. Ruchy magazynowe (wydanie/zwrot)

- GUI → koszyk → finalizacja: `app/appsvc/cart.py`
  - Rezerwacje: `issue_sessions`, `issue_session_lines`
    - INSERT/UPDATE/DELETE linii koszyka (rezerwacje)
  - Finalizacja: `CheckoutService.finalize_issue` (app/appsvc/cart.py:427)
    - SELECT linie: `SELECT item_id, qty_reserved FROM issue_session_lines WHERE session_id=:sid`
    - Pętla: `auth_repo.issue_tool(...)` (każda pozycja osobna transakcja)
    - UPDATE sesji: `UPDATE issue_sessions SET status='CONFIRMED' ...`

- Domenowe SP (transakcje na DB): `app/domain/services/*.py`
  - ISSUE: `issue.py:89` `callproc("sp_issue_tool", (employee_id, item_id, str(qty), operation_uuid))`
    - Po SP: SELECT saldo z `transactions` i `UPDATE ... issued_without_return=...` (issue.py:93,101)
  - RETURN: `return.py:59` `callproc("sp_return_tool", (...))`
  - (RW receipt): `rw.py:59` `callproc("sp_rw_receipt", (...))`

- ORM wariant (FIFO/partie) – alternatywa/benchmark: `app/dal/repo_movements.py`
  - receipt_from_document_line: INSERT `document_lines`, `lots`, `movements`, `movement_allocations`
  - issue_to_employee: SELECT lots FOR UPDATE (FIFO), INSERT `movements`, `movement_allocations`
  - return_to_warehouse: walidacja alokacji, dokument ZWROT, nowe `lots`, alokacje RETURN

Transakcje i blokady:
- RW import: jedna transakcja na dialog (`RWImportRepo.__init__`: `self.tx = self.conn.begin()`), w `insert_rw_line` używa `FOR UPDATE` na `stock` – zapobiega wyścigom przy kumulacji.
- ISSUE/RETURN: domenowe SP uruchamiane w osobnych transakcjach na każdą pozycję (AuthRepo używa `engine.begin()` per wywołanie). Możliwy częściowy sukces w pętli (rekomendacja poniżej).
- ORM ścieżka używa `with_for_update()` na `lots` (FIFO). Retry deadlock: `app/dal/retry.py`.

Potencjalne wyścigi/podwójne zapisy:
- QSpinBox → valueChanged w UI: po `add()/set_qty()` dodatkowe `setValue()` wyzwalało ponowny zapis – naprawione przez `blockSignals(True)` w: `app/ui/cart_dialog.py` i `app/ui/ops_issue_dialog.py` (patrz patch).
- Finalizacja koszyka: brak jednej transakcji otaczającej wszystkie pozycje – ryzyko częściowego zapisu (linia SP N+1). Rekomendacja: rozważyć bundlowanie (jest `domain/services/bundle.py`).

Diagram sekwencji: patrz `flows.puml` (Import RW, Issue, Return).

## C. Źródło stanu dla GUI

- Repozytorium dla listy wydawania w GUI:
  - Kartoteka listy: `app/appsvc/cart.py:193` `class StockRepository`
  - Metoda: `list_available(q, limit)` – warianty SELECT:
    1) Z tabeli `stock` + rezerwacje z `issue_session_lines` (CTE `totals`, `reservations`), aliasy:
       - `COALESCE(i.code, i.sku, CAST(i.id AS CHAR)) AS sku`
       - `COALESCE(NULLIF(TRIM(i.name),''), i.code, i.sku, CAST(i.id AS CHAR)) AS name` (patch dodany)
       - `COALESCE(i.unit, i.uom, 'SZT') AS uom`
    2) Widok `vw_stock_available` + `items`
    3) Fallbacky na `items` z `sku/uom` lub `code/unit`

- Wybór ze stanu (picker): `app/ui/stock_picker.py`
  - Używa `repo.search_stock(...)` z `AuthRepo`:
    - `app/core/auth.py:858` → SELECT z `lots` + `items`, aliasy: `sku` z `i.sku`/`i.code`, `name` = `NULLIF(TRIM(i.name),'')` (patch), `qty_available` = SUM(l.qty_available)

Wniosek – źródło prawdy:
- Mieszane: UI listy głównej preferuje `stock` (jeśli istnieje), picker i inne ścieżki – `lots`/widoki. RW import (GUI) uzupełnia `stock`, nie tworzy `lots` – może nie być widoczny w pickerze. Rekomendacja ujednolicenia poniżej.

## D. Matryca operacji SQL (CRUD)

CSV w pliku `sql_touchpoints.csv` (module,function,file:line,sql_op,table_or_view,where_or_keys,notes).

## E. Niespójności / ryzyka

- Źródło stanu: `stock` vs `lots`/widoki – UI korzysta z obu; import RW aktualizuje `stock`, nie `lots`. Picker (lots) nie zobaczy nowo przyjętych sztuk przez RW import GUI.
- Brak `FOR UPDATE` przy odczycie partii w ścieżce SP (nie w kodzie, zależność od implementacji SP). ORM ścieżka ma `FOR UPDATE`.
- QSpinBox generował podwójne zapisy – naprawione (blockSignals).
- Alias i puste nazwy: brakowało TRIM + NULLIF – uzupełniono (patchy w repozytoriach).
- Finalizacja koszyka: brak otaczającej transakcji – częściowe wydanie możliwe.

## F. Rekomendacje minimal‑patch

- Alias/normalizacja kolumn:
  - W selectach GUI używać: `code AS sku` (fallback) i `NULLIF(TRIM(name),'') AS name` – WDROŻONE w:
    - `app/appsvc/cart.py` (StockRepository.list_available + fallbacki, CartRepository.list_lines)
    - `app/core/auth.py` (search_stock)
    - `app/repo/items_repo.py`, `app/dal/items_repo.py`
- UI sygnały: blokować sygnały przy programowym `setValue()` QSpinBox – WDROŻONE w:
  - `app/ui/cart_dialog.py`, `app/ui/ops_issue_dialog.py`
- Źródło prawdy stanu:
  - Krótkoterminowo: trzymać się jednego źródła do list wydawania. Rekomendacja: widok `vw_stock_available` (bazuje na `lots` → spójny z wydaniami/zwrotami). W `StockRepository.list_available` podnieść preferencję widoku, a `stock` traktować jako LEGACY.
  - Alternatywnie: przy RW import GUI – dodatkowo wywołać SP (np. `sp_receipt_from_line`) zamiast ręcznie aktualizować `stock`, by stworzyć `lots` i pełne ślady ruchów.
- Finalizacja koszyka:
  - Rozważyć `bundle.issue_return_bundle(...)` (jest dostępny) albo otoczyć pętlę ISSUE jedną transakcją.

## G. Lista narzędzi w GUI (wydawanie)

- Repozytoria/metody:
  - `StockRepository.list_available` (app/appsvc/cart.py:198)
  - `AuthRepo.search_stock` (app/core/auth.py:858) – używane przez `StockPickerDialog`.

- SELECT‑y i aliasy (używane obecnie):
  - `StockRepository.list_available` (wariant „stock”):
    - `sku`: `COALESCE(i.code, i.sku, CAST(i.id AS CHAR)) AS sku`
    - `name`: `COALESCE(NULLIF(TRIM(i.name),''), i.code, i.sku, CAST(i.id AS CHAR)) AS name`
    - `qty_on_hand`, `qty_reserved_open`, `qty_available` z CTE i rezerwacji koszyka
  - Wariant „view”: `SELECT ... FROM vw_stock_available v JOIN items i ...` (te same aliasy)
  - Picker (`AuthRepo.search_stock`):
    - z `lots` + `items`: `i.sku` (fallback `i.code`), `NULLIF(TRIM(i.name),'') AS name`, `SUM(l.qty_available)`

- GUI – wypełnianie kolumn:
  - `app/ui/ops_issue_dialog.py`
    - Kolumna 1 (SKU): `self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(str(sku)))` (pliku: `app/ui/ops_issue_dialog.py:224`), z `item_id` w `Qt.UserRole` (`:225`)
    - Kolumna 2 (Nazwa): `:227` – wartość `name` lub `sku`
    - Kolumna 3 (JM): `:228` – `uom`
    - Ilości: `:229`..`:231` (Na stanie/Zarezerw./Dostępne)
    - Ilość w koszyku (QSpinBox): `:233`..`:238`
  - `app/ui/cart_dialog.py` – analogicznie: SKU `:239-241`, Nazwa `:242`, JM `:243`, ilości `:247-250`, QSpinBox `:251-258`.
  - `app/ui/stock_picker.py` (picker):
    - Kolumny: ID, SKU, Nazwa, JM, Dostępne; dane z `repo.search_stock`, wiersz: `self.table.setItem(r, 1, ...sku...)`, `2 → name`, `3 → uom`, `4 → qty_available`.

- Problemy znalezione i poprawki:
  - Brak `TRIM` na `name` (puste spacje) – naprawione patchami.
  - Alias `code AS sku` – obecny we wszystkich fallbackach GUI.
  - Potencjalne podwójne zapisy przez QSpinBox – zredukowane `blockSignals` przy programowym `setValue()`.
  - Identyfikacja po `item_id` w `Qt.UserRole` – obecna i właściwa (unika zależności od indeksu wiersza).

---

### Załącznik: wyniki wybranych wyszukiwań (rg)

Import RW / dokumenty:
```
app/dal/models.py:28: __tablename__ = 'document_lines'
app/dal/rw_repo_mysql.py:113: cur.callproc('sp_receipt_from_line', (...))
app/services/rw/importer.py:47: Główna funkcja importu RW → ISSUE
app/dal/rw_import_repo.py:204: INSERT INTO document_lines(...)
schema.sql:29: CREATE TABLE `document_lines` (...)
```

Stany i ruchy:
```
schema.sql:162: CREATE TABLE `lots` (...)
schema.sql:182: CREATE TABLE `movement_allocations` (...)
schema.sql:197: CREATE TABLE `movements` (...)
schema.sql:227: CREATE TABLE `transaction_items` (...)
schema.sql:245: CREATE TABLE `transactions` (...)
app/dal/rw_import_repo.py:216: INSERT INTO movements(...)
```

Transakcje/locki:
```
app/dal/rw_import_repo.py:155: SELECT ... FROM stock ... FOR UPDATE
app/domain/services/issue.py:93: SELECT COALESCE(SUM(...)) FROM transactions ...
app/domain/services/issue.py:101: UPDATE transactions SET issued_without_return=...
```

Widoki/aliasy:
```
schema.sql:299: CREATE VIEW `vw_stock_available` AS WITH reservations ... JOIN vw_stock_on_hand ...
schema.sql:307: CREATE VIEW `vw_stock_on_hand` AS SELECT i.id, SUM(l.qty_available)...
```

Koszyk/sesje:
```
app/appsvc/cart.py:54: INSERT INTO issue_sessions (...)
app/appsvc/cart.py:145: INSERT INTO issue_session_lines (...)
app/appsvc/cart.py:152: UPDATE issue_session_lines SET qty_reserved=...
app/appsvc/cart.py:160: DELETE FROM issue_session_lines WHERE session_id=:sid
app/appsvc/cart.py:455: UPDATE issue_sessions SET status='CONFIRMED', confirmed_at=...
```

LEGACY:
- Tabela `stock` i operacje na niej w RW import GUI – traktować jako LEGACY źródło; rekomendowane przejście na `lots` + widoki.

