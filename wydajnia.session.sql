SELECT table_name, column_name, column_type, is_nullable, column_key, extra
FROM information_schema.columns
WHERE table_schema = 'wydajnia'
ORDER BY table_name, ordinal_position;
