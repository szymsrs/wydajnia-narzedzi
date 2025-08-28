/*
 Auto-generated schema snapshot by tools/sync_schema.py
 Generated: 2025-08-28 13:07:11
*/


-- Database: `wydajnia`
SET FOREIGN_KEY_CHECKS=0;

-- ----------------------------
-- Table structure for `audit_logs`
-- ----------------------------
DROP TABLE IF EXISTS `audit_logs`;
CREATE TABLE `audit_logs` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `ts` timestamp NULL DEFAULT current_timestamp(),
  `os_user` varchar(100) DEFAULT NULL,
  `workstation_id` varchar(50) DEFAULT NULL,
  `action` varchar(255) DEFAULT NULL,
  `result` varchar(50) DEFAULT NULL,
  `details` text DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table structure for `document_lines`
-- ----------------------------
DROP TABLE IF EXISTS `document_lines`;
CREATE TABLE `document_lines` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `document_id` bigint(20) NOT NULL,
  `item_id` int(11) NOT NULL,
  `qty` decimal(12,3) NOT NULL,
  `unit_price_netto` decimal(12,4) NOT NULL,
  `line_netto` decimal(12,2) NOT NULL,
  `vat_proc` decimal(5,2) DEFAULT NULL,
  `line_brutto` decimal(12,2) DEFAULT NULL,
  `currency` char(3) NOT NULL DEFAULT 'PLN',
  `parse_confidence` decimal(5,2) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_dl_doc` (`document_id`),
  KEY `ix_dl_item` (`item_id`),
  CONSTRAINT `fk_dl_doc` FOREIGN KEY (`document_id`) REFERENCES `documents` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `fk_dl_item_ok` FOREIGN KEY (`item_id`) REFERENCES `items` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=54 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;

-- ----------------------------
-- Table structure for `documents`
-- ----------------------------
DROP TABLE IF EXISTS `documents`;
CREATE TABLE `documents` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `doc_type` enum('PRZYJECIE','FAKTURA','RW','ZWROT','INNE') NOT NULL,
  `number` varchar(64) NOT NULL,
  `doc_date` date NOT NULL,
  `currency` char(3) NOT NULL DEFAULT 'PLN',
  `suma_netto` decimal(12,2) DEFAULT NULL,
  `suma_vat` decimal(12,2) DEFAULT NULL,
  `suma_brutto` decimal(12,2) DEFAULT NULL,
  `parse_conf` tinyint(4) DEFAULT NULL,
  `parse_warnings` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`parse_warnings`)),
  `parse_confidence` decimal(5,2) DEFAULT NULL,
  `source_file` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_documents_doctype_number` (`doc_type`,`number`),
  KEY `idx_documents_number` (`number`),
  KEY `idx_documents_date` (`doc_date`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table structure for `employees`
-- ----------------------------
DROP TABLE IF EXISTS `employees`;
CREATE TABLE `employees` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `rfid_uid` varchar(32) DEFAULT NULL,
  `first_name` varchar(100) NOT NULL,
  `last_name` varchar(100) NOT NULL,
  `is_admin` tinyint(1) NOT NULL DEFAULT 0,
  `username` varchar(50) DEFAULT NULL,
  `password_hash` varchar(255) DEFAULT NULL,
  `pin_hash` varchar(255) DEFAULT NULL,
  `pin_plain` varchar(8) DEFAULT NULL,
  `role` enum('operator','kierownik','audytor','admin') NOT NULL,
  `active` tinyint(1) DEFAULT 1,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `rfid_uid` (`rfid_uid`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `uq_employees_rfid_uid` (`rfid_uid`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table structure for `issue_session_lines`
-- ----------------------------
DROP TABLE IF EXISTS `issue_session_lines`;
CREATE TABLE `issue_session_lines` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `session_id` bigint(20) NOT NULL,
  `item_id` int(11) NOT NULL,
  `qty_reserved` decimal(12,3) NOT NULL CHECK (`qty_reserved` > 0),
  PRIMARY KEY (`id`),
  KEY `idx_issue_lines_session_item` (`session_id`,`item_id`),
  KEY `idx_issue_lines_item` (`item_id`),
  CONSTRAINT `fk_issue_session_lines_session` FOREIGN KEY (`session_id`) REFERENCES `issue_sessions` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table structure for `issue_sessions`
-- ----------------------------
DROP TABLE IF EXISTS `issue_sessions`;
CREATE TABLE `issue_sessions` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `station_id` varchar(64) DEFAULT NULL,
  `operator_user_id` int(11) DEFAULT NULL,
  `employee_id` int(11) DEFAULT NULL,
  `status` enum('OPEN','CONFIRMED','CANCELLED') NOT NULL DEFAULT 'OPEN',
  `started_at` datetime NOT NULL DEFAULT current_timestamp(),
  `expires_at` datetime DEFAULT NULL,
  `confirmed_at` datetime DEFAULT NULL,
  `operation_uuid` char(36) DEFAULT NULL,
  `note` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_issue_sessions_status` (`status`),
  KEY `idx_issue_sessions_expires` (`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table structure for `items`
-- ----------------------------
DROP TABLE IF EXISTS `items`;
CREATE TABLE `items` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `code` varchar(64) NOT NULL,
  `name` varchar(255) NOT NULL,
  `unit` varchar(16) NOT NULL DEFAULT 'SZT',
  `min_stock` int(11) DEFAULT 0,
  `max_per_employee` int(11) DEFAULT NULL,
  `active` tinyint(1) DEFAULT 1,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB AUTO_INCREMENT=58 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ROW_FORMAT=DYNAMIC;

-- ----------------------------
-- Table structure for `locations`
-- ----------------------------
DROP TABLE IF EXISTS `locations`;
CREATE TABLE `locations` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `type` enum('WAREHOUSE','EMPLOYEE','SCRAP') NOT NULL,
  `employee_id` bigint(20) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_locations_employee` (`employee_id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table structure for `lots`
-- ----------------------------
DROP TABLE IF EXISTS `lots`;
CREATE TABLE `lots` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `item_id` bigint(20) NOT NULL,
  `document_line_id` bigint(20) NOT NULL,
  `qty_received` decimal(12,3) NOT NULL,
  `qty_available` decimal(12,3) NOT NULL,
  `unit_cost_netto` decimal(12,4) NOT NULL,
  `currency` char(3) NOT NULL DEFAULT 'PLN',
  `ts` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_lots_item` (`item_id`,`ts`,`id`),
  KEY `fk_lots_dl` (`document_line_id`),
  CONSTRAINT `fk_lots_dl` FOREIGN KEY (`document_line_id`) REFERENCES `document_lines` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT `chk_lots_qty_nonneg` CHECK (`qty_available` >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table structure for `movement_allocations`
-- ----------------------------
DROP TABLE IF EXISTS `movement_allocations`;
CREATE TABLE `movement_allocations` (
  `movement_id` bigint(20) NOT NULL,
  `lot_id` bigint(20) NOT NULL,
  `qty` decimal(12,3) NOT NULL,
  `unit_cost_netto` decimal(12,4) NOT NULL,
  PRIMARY KEY (`movement_id`,`lot_id`),
  KEY `fk_ma_lot` (`lot_id`),
  CONSTRAINT `fk_ma_lot` FOREIGN KEY (`lot_id`) REFERENCES `lots` (`id`) ON UPDATE CASCADE,
  CONSTRAINT `fk_ma_mv` FOREIGN KEY (`movement_id`) REFERENCES `movements` (`id`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table structure for `movements`
-- ----------------------------
DROP TABLE IF EXISTS `movements`;
CREATE TABLE `movements` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `ts` datetime NOT NULL DEFAULT current_timestamp(),
  `item_id` bigint(20) DEFAULT NULL,
  `qty` decimal(12,3) DEFAULT NULL,
  `from_location_id` bigint(20) DEFAULT NULL,
  `to_location_id` bigint(20) DEFAULT NULL,
  `movement_type` enum('RECEIPT','ISSUE','RETURN','SCRAP','ADJUST') NOT NULL,
  `document_line_id` bigint(20) DEFAULT NULL,
  `operation_uuid` char(36) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_movements_item_ts` (`item_id`,`ts`)
) ENGINE=InnoDB AUTO_INCREMENT=40 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table structure for `stock`
-- ----------------------------
DROP TABLE IF EXISTS `stock`;
CREATE TABLE `stock` (
  `item_id` int(11) NOT NULL,
  `quantity` int(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`item_id`),
  CONSTRAINT `stock_ibfk_1` FOREIGN KEY (`item_id`) REFERENCES `items` (`id`),
  CONSTRAINT `chk_stock_qty_nonneg` CHECK (`quantity` >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table structure for `transaction_items`
-- ----------------------------
DROP TABLE IF EXISTS `transaction_items`;
CREATE TABLE `transaction_items` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `operation_uuid` char(36) NOT NULL,
  `item_id` int(11) NOT NULL,
  `quantity` decimal(12,3) NOT NULL,
  `direction` enum('OUT','IN') NOT NULL,
  `reason` varchar(64) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_ti_op` (`operation_uuid`),
  KEY `ix_ti_item` (`item_id`),
  CONSTRAINT `fk_ti_item` FOREIGN KEY (`item_id`) REFERENCES `items` (`id`),
  CONSTRAINT `fk_ti_tx` FOREIGN KEY (`operation_uuid`) REFERENCES `transactions` (`operation_uuid`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------
-- Table structure for `transactions`
-- ----------------------------
DROP TABLE IF EXISTS `transactions`;
CREATE TABLE `transactions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `operation_uuid` char(36) NOT NULL,
  `movement_type` varchar(20) NOT NULL,
  `employee_id` int(11) NOT NULL,
  `item_id` int(11) DEFAULT NULL,
  `quantity` int(11) DEFAULT NULL,
  `type` enum('wydanie','zwrot','złom','adjust') DEFAULT NULL,
  `issued_without_return` tinyint(1) DEFAULT 0,
  `reason` text DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  `rfid_confirmed` tinyint(1) DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_transactions_operation_uuid` (`operation_uuid`),
  KEY `item_id` (`item_id`),
  KEY `idx_transactions_uuid_confirmed` (`operation_uuid`,`rfid_confirmed`),
  KEY `idx_transactions_iwr` (`issued_without_return`),
  KEY `idx_trx_employee` (`employee_id`),
  KEY `idx_tx_emp_item` (`employee_id`,`item_id`),
  KEY `idx_tx_iwr` (`issued_without_return`),
  CONSTRAINT `fk_trx_employee` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `transactions_ibfk_3` FOREIGN KEY (`item_id`) REFERENCES `items` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

SET FOREIGN_KEY_CHECKS=1;

-- ----------------------------
-- View structure for `v_employee_holdings`
-- ----------------------------
DROP VIEW IF EXISTS `v_employee_holdings`;
CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `v_employee_holdings` AS with emp_issue as (select `ma`.`lot_id` AS `lot_id`,`l`.`item_id` AS `item_id`,`l`.`unit_cost_netto` AS `unit_cost_netto`,`m`.`to_location_id` AS `emp_loc`,`ma`.`qty` AS `qty` from ((`movement_allocations` `ma` join `movements` `m` on(`m`.`id` = `ma`.`movement_id` and `m`.`movement_type` = 'ISSUE')) join `lots` `l` on(`l`.`id` = `ma`.`lot_id`))), emp_return as (select `ma`.`lot_id` AS `lot_id`,`l`.`item_id` AS `item_id`,`l`.`unit_cost_netto` AS `unit_cost_netto`,`m`.`from_location_id` AS `emp_loc`,`ma`.`qty` AS `qty` from ((`movement_allocations` `ma` join `movements` `m` on(`m`.`id` = `ma`.`movement_id` and `m`.`movement_type` = 'RETURN')) join `lots` `l` on(`l`.`id` = `ma`.`lot_id`))), emp_scrap as (select `ma`.`lot_id` AS `lot_id`,`l`.`item_id` AS `item_id`,`l`.`unit_cost_netto` AS `unit_cost_netto`,`m`.`from_location_id` AS `emp_loc`,`ma`.`qty` AS `qty` from ((`movement_allocations` `ma` join `movements` `m` on(`m`.`id` = `ma`.`movement_id` and `m`.`movement_type` = 'SCRAP')) join `lots` `l` on(`l`.`id` = `ma`.`lot_id`)))select `ei`.`emp_loc` AS `emp_loc`,`ei`.`item_id` AS `item_id`,sum(`ei`.`qty`) - coalesce(sum(`er`.`qty`),0) - coalesce(sum(`es`.`qty`),0) AS `qty_now`,sum(`ei`.`qty` * `ei`.`unit_cost_netto`) - coalesce(sum(`er`.`qty` * `er`.`unit_cost_netto`),0) - coalesce(sum(`es`.`qty` * `es`.`unit_cost_netto`),0) AS `value_now` from ((`emp_issue` `ei` left join `emp_return` `er` on(`er`.`emp_loc` = `ei`.`emp_loc` and `er`.`item_id` = `ei`.`item_id` and `er`.`lot_id` = `ei`.`lot_id`)) left join `emp_scrap` `es` on(`es`.`emp_loc` = `ei`.`emp_loc` and `es`.`item_id` = `ei`.`item_id` and `es`.`lot_id` = `ei`.`lot_id`)) group by `ei`.`emp_loc`,`ei`.`item_id` having `qty_now` > 0;

-- ----------------------------
-- View structure for `vw_employee_card`
-- ----------------------------
DROP VIEW IF EXISTS `vw_employee_card`;
CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `vw_employee_card` AS select `e`.`id` AS `employee_id`,`e`.`first_name` AS `first_name`,`e`.`last_name` AS `last_name`,`ti`.`item_id` AS `item_id`,sum(case when `ti`.`direction` = 'OUT' then `ti`.`quantity` when `ti`.`direction` = 'IN' then -`ti`.`quantity` else 0 end) AS `balance_qty`,min(`t`.`created_at`) AS `first_op`,max(`t`.`created_at`) AS `last_op` from ((`employees` `e` left join `transactions` `t` on(`t`.`employee_id` = `e`.`id`)) left join `transaction_items` `ti` on(`ti`.`operation_uuid` = `t`.`operation_uuid`)) group by `e`.`id`,`e`.`first_name`,`e`.`last_name`,`ti`.`item_id`;

-- ----------------------------
-- View structure for `vw_exceptions`
-- ----------------------------
DROP VIEW IF EXISTS `vw_exceptions`;
CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `vw_exceptions` AS select `transactions`.`id` AS `id`,`transactions`.`created_at` AS `created_at`,`transactions`.`employee_id` AS `employee_id`,`transactions`.`item_id` AS `item_id`,`transactions`.`quantity` AS `quantity`,'ISSUE_NO_RETURN' AS `exception_type` from `transactions` where `transactions`.`movement_type` = 'ISSUE' and `transactions`.`issued_without_return` = 1;

-- ----------------------------
-- View structure for `vw_rw_summary`
-- ----------------------------
DROP VIEW IF EXISTS `vw_rw_summary`;
CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `vw_rw_summary` AS select `d`.`id` AS `rw_id`,`d`.`number` AS `rw_number`,`d`.`doc_date` AS `rw_date`,`dl`.`item_id` AS `item_id`,sum(`dl`.`qty`) AS `qty_total` from (`documents` `d` join `document_lines` `dl` on(`dl`.`document_id` = `d`.`id`)) where `d`.`doc_type` = 'RW' group by `d`.`id`,`d`.`number`,`d`.`doc_date`,`dl`.`item_id`;

-- ----------------------------
-- View structure for `vw_stock_available`
-- ----------------------------
DROP VIEW IF EXISTS `vw_stock_available`;
CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `vw_stock_available` AS with reservations as (select `l`.`item_id` AS `item_id`,coalesce(sum(`l`.`qty_reserved`),0) AS `qty_reserved_open` from (`issue_sessions` `s` join `issue_session_lines` `l` on(`l`.`session_id` = `s`.`id`)) where `s`.`status` = 'OPEN' and (`s`.`expires_at` is null or `s`.`expires_at` > current_timestamp()) group by `l`.`item_id`)select `oh`.`item_id` AS `item_id`,`oh`.`qty_on_hand` AS `qty_on_hand`,coalesce(`r`.`qty_reserved_open`,0) AS `qty_reserved_open`,`oh`.`qty_on_hand` - coalesce(`r`.`qty_reserved_open`,0) AS `qty_available` from (`vw_stock_on_hand` `oh` left join `reservations` `r` on(`r`.`item_id` = `oh`.`item_id`));

-- ----------------------------
-- View structure for `vw_stock_on_hand`
-- ----------------------------
DROP VIEW IF EXISTS `vw_stock_on_hand`;
CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `vw_stock_on_hand` AS select `i`.`id` AS `item_id`,coalesce(sum(`l`.`qty_available`),0) AS `qty_on_hand` from (`items` `i` left join `lots` `l` on(`l`.`item_id` = `i`.`id`)) group by `i`.`id`;

-- ----------------------------
-- Trigger structure for `lots_non_negative`
-- ----------------------------
DROP TRIGGER IF EXISTS `lots_non_negative`;
CREATE TRIGGER `lots_non_negative` BEFORE UPDATE ON `lots` FOR EACH ROW BEGIN
  IF NEW.qty_available < 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='qty_available < 0';
  END IF;
END;

-- ----------------------------
-- Trigger structure for `trg_lots_nonneg`
-- ----------------------------
DROP TRIGGER IF EXISTS `trg_lots_nonneg`;
CREATE TRIGGER `trg_lots_nonneg` BEFORE UPDATE ON `lots` FOR EACH ROW BEGIN
  IF NEW.qty_available < 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Negative lot quantity';
  END IF;
END;

-- ----------------------------
-- Trigger structure for `trg_stock_nonneg`
-- ----------------------------
DROP TRIGGER IF EXISTS `trg_stock_nonneg`;
CREATE TRIGGER `trg_stock_nonneg` BEFORE INSERT ON `stock` FOR EACH ROW BEGIN
  IF NEW.quantity < 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Negative stock quantity';
  END IF;
END;

-- ----------------------------
-- Trigger structure for `trg_stock_nonneg_u`
-- ----------------------------
DROP TRIGGER IF EXISTS `trg_stock_nonneg_u`;
CREATE TRIGGER `trg_stock_nonneg_u` BEFORE UPDATE ON `stock` FOR EACH ROW BEGIN
  IF NEW.quantity < 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Negative stock quantity';
  END IF;
END;
