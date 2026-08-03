-- SQL миграции для функционала пересылки сообщений и выделения
-- Выполнять последовательно

-- 1. Добавляем поля для отслеживания пересланных сообщений в таблицу messages
ALTER TABLE messages 
ADD COLUMN IF NOT EXISTS is_forwarded BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS forwarded_from VARCHAR(255),  -- От кого было переслано (имя отправителя оригинала)
ADD COLUMN IF NOT EXISTS forwarded_at TIMESTAMP;       -- Когда было переслано

-- 2. Добавляем индекс для ускорения поиска пересланных сообщений (опционально)
CREATE INDEX IF NOT EXISTS idx_messages_is_forwarded ON messages(is_forwarded);

-- 3. Комментарий к новым полям
COMMENT ON COLUMN messages.is_forwarded IS 'Флаг indicating что сообщение является пересланным';
COMMENT ON COLUMN messages.forwarded_from IS 'Имя отправителя оригинального сообщения';
COMMENT ON COLUMN messages.forwarded_at IS 'Время пересылки сообщения';

-- Пример использования новых полей при вставке пересланного сообщения:
-- INSERT INTO messages (chat_id, sender_id, message_text, is_forwarded, forwarded_from, forwarded_at)
-- VALUES (1, 123, 'Пересланный текст', TRUE, 'Иванов Иван', NOW());

-- Для отображения информации о пересланном сообщении в UI:
-- SELECT m.id, m.message_text, m.is_forwarded, m.forwarded_from, m.forwarded_at,
--        e.last_name || ' ' || e.first_name as current_sender_name
-- FROM messages m
-- JOIN employees e ON m.sender_id = e.id
-- WHERE m.chat_id = <chat_id>
-- ORDER BY m.created_at ASC;
