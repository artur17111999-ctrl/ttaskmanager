-- Скриншоты, вставленные из буфера обмена, хранятся рядом с сущностью.
CREATE TABLE IF NOT EXISTS image_attachments (
    id SERIAL PRIMARY KEY,
    owner_type VARCHAR(20) NOT NULL CHECK (owner_type IN ('task', 'message', 'comment')),
    owner_id INTEGER NOT NULL,
    image_data BYTEA NOT NULL,
    file_name VARCHAR(255) NOT NULL DEFAULT 'screenshot.png',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_image_attachments_owner
    ON image_attachments(owner_type, owner_id);
