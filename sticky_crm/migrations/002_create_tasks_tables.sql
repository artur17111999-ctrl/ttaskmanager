-- Миграция для создания таблиц задач

-- Таблица тегов задач
CREATE TABLE IF NOT EXISTS task_tags (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    color VARCHAR(7) DEFAULT '#808080',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица задач
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    short_description TEXT,
    description TEXT,
    status VARCHAR(50) DEFAULT 'new',
    priority VARCHAR(50) DEFAULT 'Средний',
    deadline DATE,
    author_id INTEGER NOT NULL REFERENCES employees(id),
    executor_id INTEGER NOT NULL REFERENCES employees(id),
    created_by INTEGER NOT NULL REFERENCES employees(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица наблюдателей задач
CREATE TABLE IF NOT EXISTS task_observers (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    employee_id INTEGER NOT NULL REFERENCES employees(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(task_id, employee_id)
);

-- Таблица связи задач и тегов
CREATE TABLE IF NOT EXISTS task_tags_link (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES task_tags(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(task_id, tag_id)
);

-- Таблица файлов задач (для прикрепленных файлов)
CREATE TABLE IF NOT EXISTS task_files (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    file_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_size BIGINT,
    uploaded_by INTEGER NOT NULL REFERENCES employees(id),
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для ускорения поиска
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_executor ON tasks(executor_id);
CREATE INDEX IF NOT EXISTS idx_tasks_author ON tasks(author_id);
CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline);
CREATE INDEX IF NOT EXISTS idx_task_observers_task ON task_observers(task_id);
CREATE INDEX IF NOT EXISTS idx_task_observers_employee ON task_observers(employee_id);
CREATE INDEX IF NOT EXISTS idx_task_tags_link_task ON task_tags_link(task_id);
CREATE INDEX IF NOT EXISTS idx_task_tags_link_tag ON task_tags_link(tag_id);

-- Добавляем несколько стандартных тегов
INSERT INTO task_tags (name, color) VALUES 
    ('Баг', '#f44336'),
    ('Фича', '#4caf50'),
    ('Улучшение', '#2196f3'),
    ('Документация', '#ff9800'),
    ('Тесты', '#9c27b0')
ON CONFLICT (name) DO NOTHING;
