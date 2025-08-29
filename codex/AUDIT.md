# Codebase Audit

## Formatting
- Numerous style violations (E701/E702) from `ruff` in GUI scripts, e.g. chained statements in `import_rw_gui.py` and `users_widget.py`【350362†L1-L92】.

## Typing
- `mypy --strict` reports missing annotations and invalid types across modules, e.g. incompatible return type in `exceptions_repo.py`【251358†L42-L43】 and missing generics in `reports_repo.py`【251358†L38-L39】.

## Bugs
- `ItemsRepo.find_items` built search pattern with surrounding `%` causing mismatched parameters; adjusted to use SQL `CONCAT` and raw `q`【6b9e3f†L21-L47】.
- `ItemsRepo.get_item_id_by_sku` executed fallback even when query returned no row, leading to extra query and test failure; now fallback only on `OperationalError` and uses named parameter `sku`【6b9e3f†L49-L62】.
- `issue.issue_tool` assumed cursor provided `fetchone`; stub cursors raised `AttributeError`. Added guard to skip extra queries when cursor lacks methods【14a39b†L85-L107】.

## Dead Code
- `app/infra/healthcheck.py` provides a DB ping utility but is not referenced elsewhere【9eaa97†L1-L5】【55c41e†L1-L9】.

## Security
- Debug helper `_dbg` prints messages to stdout which may expose sensitive information in production logs【4d54c7†L31-L34】.

## Dependencies
- Outdated packages detected: `ruff`, `platformdirs`, `pydantic_core`, `pyright`, `typing_extensions`【1d0355†L1-L7】.

## Testing
- Test suite now passes (`7 passed`) with overall coverage ~4%【4751d5†L1-L71】.
- `mypy --strict` still reports 498 errors【251358†L1-L103】.
- `ruff` check reports 150 formatting issues【afdba1†L1-L60】.
