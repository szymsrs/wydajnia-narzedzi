# Wydajnia Narzędzi – Aktualne Założenia

## 1. Cel i zakres
Aplikacja desktopowa (.exe, Windows) do obsługi wydawania, zwrotów, złomowania narzędzi i materiałów 
z „wydajni narzędzi” w firmie, zintegrowana z bazą danych MariaDB na NAS. 
System działa w zamkniętej sieci wewnętrznej (brak dostępu z zewnątrz).

## 2. Role i uprawnienia
- **Operator wydajni** – wykonuje wydania, zwroty, złom, importuje RW, przegląda raporty.
- **Kierownik** – jak operator + zatwierdzanie inwentaryzacji i wykonywanie Adjust.
- **Audytor** – odczyt raportów i logów.
- **Administrator** – zarządzanie pracownikami, kartami RFID, PIN-ami, katalogiem pozycji, progami minimalnego stanu.

## 3. Autoryzacja i kontrola
- Każda operacja wymaga potwierdzenia **kartą RFID lub PIN-em** pracownika.  
- Proces jest dwuetapowy: operator przygotowuje koszyk → pracownik potwierdza → operator zatwierdza.  
- Brak możliwości zatwierdzenia operacji bez uwierzytelnienia.

## 4. Obsługa limitów
- Brak twardej blokady przy przekroczeniu max na pracownika.  
- Jeśli wydanie przekracza rekomendowany limit lub nie ma zwrotu poprzedniego egzemplarza, system oznacza ruch flagą `issued_without_return=true` i tworzy alert w panelu **„Wyjątki”**.

## 5. Funkcje główne
- Import RW (PDF) – parser regex ze stałego szablonu PDF, weryfikacja i zatwierdzenie.
- Wydanie do pracownika – koszyk pozycji → karta/PIN → zatwierdzenie.
- Zwrot na stan ogólny – karta/PIN → wybór ilości → zatwierdzenie.
- Złomowanie – karta/PIN → wybór ilości → powód (opcjonalny) → zatwierdzenie.
- Inwentaryzacja – arkusz porównania stanu systemowego z fizycznym, możliwość Adjust (tylko Kierownik, z powodem).
- Raporty – karty pracowników, zużycie miesięczne, złom, min. stany, RW→zużycie.
- Panel „Wyjątki” – wydania bez zwrotu, złom bez powodu, adjusty.

## 6. Audyt i logi
- Log aplikacyjny: czas, użytkownik OS, stanowisko, akcja, wynik, szczegóły.  
- Wyjątki oznaczane w logu i widoczne w raportach.  
- Adjusty logowane z wartościami przed/po, podpisami osób i powodem.  
- Eksport audytu do CSV/PDF.

## 7. GUI i ergonomia
- Nowoczesny interfejs z obsługą myszki i klawiatury.  
- Layout 3-strefowy: nawigacja, obszar główny, panel kontekstu.  
- Duże przyciski, tryb jasny/dark, skróty klawiaturowe.  
- Ekran „Przyłóż kartę/PIN” – modal z dużym komunikatem.  
- W GUI przewidziano: **QTableView + QAbstractTableModel** dla wydajności, zakładkę zarządzania użytkownikami (edycja, hashowanie PIN-ów bcrypt).

## 8. Struktura aplikacji
```
/App
  /bin      – pliki exe, biblioteki
  /ui       – motywy, ikony, fonty
  /config   – pliki konfiguracyjne (JSON/INI)
  /logs     – logi aplikacji
  /cache    – pamięć podręczna
```

## 9. Konfiguracja
- `config/app.json` z ustawieniami DB, identyfikatorem stanowiska, motywem UI, progami min. stanu.  
- Ustawienia alertów i raportów wyjątków.

## 10. Zasady spójności i bezpieczeństwa
- Transakcje z blokadami `FOR UPDATE` dla utrzymania spójności.  
- Brak stanów ujemnych (walidacja w DB + UI).  
- Idempotencja operacji (`operation_uuid`).

## 11. Raporty
- Karta pracownika (stan + historia).  
- Zużycie miesięczne.  
- Złom (z/bez powodu).  
- Min. stany.  
- Konsumpcja z RW.  
- Wyjątki.  
- Eksport CSV/PDF z filtrami.

## 12. Definition of Done – wersja 1.0
- Wydania/zwroty/złomy wyłącznie z kartą lub PIN-em.  
- Obsługa flagi „wydanie bez zwrotu” i raportowanie wyjątków.  
- Import RW z weryfikacją.  
- Inwentaryzacja z Adjust.  
- Raporty i eksporty.  
- Nowoczesne GUI.  
- Struktura katalogowa i konfiguracja zewnętrzna.  
- Pełny audyt działań.

---

# Struktura bazy danych (MariaDB)

```sql
-- Najważniejsze tabele:

employees(id, rfid_uid, first_name, last_name, username, password_hash, pin_hash, role, active, created_at)
items(id, code, name, unit, min_stock, max_per_employee, active, created_at)
locations(id, name, type[WAREHOUSE|EMPLOYEE|SCRAP], employee_id)
lots(id, item_id, document_line_id, qty_received, qty_available, unit_cost_netto, currency, ts)
movements(id, ts, item_id, qty, from_location_id, to_location_id, movement_type, document_line_id)
movement_allocations(movement_id, lot_id, qty, unit_cost_netto)
documents(id, doc_type, number, doc_date, currency, suma_netto, suma_vat, suma_brutto)
document_lines(id, document_id, item_id, qty, unit_price_netto, line_netto, vat_proc, line_brutto, currency)
transactions(id, operation_uuid, employee_id, operator_id, item_id, quantity, type, issued_without_return, reason, created_at)
audit_logs(id, ts, os_user, workstation_id, action, result, details)
stock(item_id, quantity)

-- Widoki:
v_employee_holdings(emp_loc, item_id, qty_now, value_now)

-- Procedury (przykłady):
sp_issue_to_employee(...)
sp_return_from_employee(...)
sp_receipt_from_line(...)
```
