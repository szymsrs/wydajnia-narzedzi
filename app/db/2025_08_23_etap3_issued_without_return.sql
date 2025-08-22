-- Etap 3: issued_without_return flag and exceptions view
ALTER TABLE IF EXISTS transactions
  ADD COLUMN IF NOT EXISTS issued_without_return TINYINT(1) DEFAULT 0,
  ADD INDEX IF NOT EXISTS idx_transactions_iwr (issued_without_return);

CREATE OR REPLACE VIEW vw_exceptions AS
  SELECT
    t.operation_uuid,
    t.employee_id,
    CONCAT(e.first_name,' ',e.last_name) AS employee,
    e.username AS login,
    t.item_id,
    i.name AS item,
    t.quantity,
    t.movement_type,
    t.created_at
  FROM transactions t
  JOIN employees e ON e.id = t.employee_id
  JOIN items i ON i.id = t.item_id
  WHERE t.issued_without_return = 1;
