"""
Работа с базой данных.
"""

import psycopg2
from psycopg2 import Binary
from datetime import datetime
from config import DB_CONFIG

def _ensure_stickies_table(cursor):
    cursor.execute("""CREATE TABLE IF NOT EXISTS stickies (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
        source_type VARCHAR(20) NOT NULL,
        source_id INTEGER NOT NULL,
        title VARCHAR(255) NOT NULL DEFAULT '',
        text TEXT NOT NULL DEFAULT '',
        color VARCHAR(20) NOT NULL DEFAULT '#fef3a5',
        pin_mode VARCHAR(30) NOT NULL DEFAULT 'bottom_movable',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stickies_user ON stickies(user_id)")
    cursor.execute("ALTER TABLE stickies ADD COLUMN IF NOT EXISTS pos_x INTEGER")
    cursor.execute("ALTER TABLE stickies ADD COLUMN IF NOT EXISTS pos_y INTEGER")
    cursor.execute("ALTER TABLE stickies ADD COLUMN IF NOT EXISTS width INTEGER NOT NULL DEFAULT 340")
    cursor.execute("ALTER TABLE stickies ADD COLUMN IF NOT EXISTS height INTEGER NOT NULL DEFAULT 274")
    cursor.execute("ALTER TABLE stickies ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN NOT NULL DEFAULT FALSE")
    cursor.execute("ALTER TABLE stickies ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE")


def create_sticky(user_id, source_type, source_id, title, text, color='#fef3a5', pin_mode='bottom_movable', geometry=None):
    conn = get_connection()
    if not conn:
        return None
    cursor = None
    try:
        cursor = conn.cursor()
        _ensure_stickies_table(cursor)
        x, y, width, height = geometry or (None, None, 340, 274)
        cursor.execute("""INSERT INTO stickies
            (user_id, source_type, source_id, title, text, color, pin_mode, pos_x, pos_y, width, height)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (user_id, source_type, source_id, title or '', text or '', color, pin_mode, x, y, width, height))
        sticky_id = cursor.fetchone()[0]
        conn.commit()
        return sticky_id
    except Exception as error:
        conn.rollback()
        print(f"Ошибка создания стика: {error}")
        return None
    finally:
        if cursor: cursor.close()
        conn.close()


def update_sticky(sticky_id, user_id, title, text, color, pin_mode, geometry=None):
    conn = get_connection()
    if not conn:
        return False
    cursor = None
    try:
        cursor = conn.cursor()
        _ensure_stickies_table(cursor)
        x, y, width, height = geometry or (None, None, 340, 274)
        cursor.execute("""UPDATE stickies SET title=%s,text=%s,color=%s,pin_mode=%s,
            pos_x=%s,pos_y=%s,width=%s,height=%s,updated_at=CURRENT_TIMESTAMP
            WHERE id=%s AND user_id=%s""",
            (title or '', text or '', color, pin_mode, x, y, width, height, sticky_id, user_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as error:
        conn.rollback()
        print(f"Ошибка сохранения стика: {error}")
        return False
    finally:
        if cursor: cursor.close()
        conn.close()


def get_user_stickies(user_id):
    conn = get_connection()
    if not conn: return []
    cursor = None
    try:
        cursor = conn.cursor()
        _ensure_stickies_table(cursor)
        cursor.execute("""SELECT id, source_type, source_id, title, text, color, pin_mode, pos_x, pos_y, width, height
            FROM stickies WHERE user_id=%s AND is_hidden=FALSE AND is_archived=FALSE ORDER BY updated_at DESC""", (user_id,))
        result = [{'id': r[0], 'user_id': user_id, 'source_type': r[1], 'source_id': r[2], 'title': r[3],
                 'text': r[4], 'color': r[5], 'pin_mode': r[6], 'pos_x': r[7], 'pos_y': r[8],
                 'width': r[9], 'height': r[10]} for r in cursor.fetchall()]
        conn.commit()
        return result
    finally:
        if cursor: cursor.close()
        conn.close()


def get_stickies_overview(user_id):
    conn = get_connection()
    if not conn: return []
    cursor = None
    try:
        cursor = conn.cursor()
        _ensure_stickies_table(cursor)
        cursor.execute("""
            SELECT s.id, s.source_type, s.source_id, s.title, s.text, s.color, s.pin_mode,
                   s.pos_x, s.pos_y, s.width, s.height, s.is_hidden, s.is_archived,
                   s.created_at, s.updated_at,
                   t.title, COALESCE(ts.title, t.status),
                   m.message_text, m.chat_id, m.is_deleted
            FROM stickies s
            LEFT JOIN tasks t ON s.source_type='task' AND t.id=s.source_id
            LEFT JOIN task_statuses ts ON t.status_id=ts.id
            LEFT JOIN messages m ON s.source_type='message' AND m.id=s.source_id
            WHERE s.user_id=%s
            ORDER BY s.updated_at DESC
        """, (user_id,))
        rows = []
        for r in cursor.fetchall():
            rows.append({
                'id': r[0], 'user_id': user_id, 'source_type': r[1], 'source_id': r[2], 'title': r[3], 'text': r[4],
                'color': r[5], 'pin_mode': r[6], 'pos_x': r[7], 'pos_y': r[8], 'width': r[9],
                'height': r[10], 'is_hidden': r[11], 'is_archived': r[12], 'created_at': r[13],
                'updated_at': r[14], 'task_title': r[15], 'task_status': r[16],
                'message_text': r[17], 'chat_id': r[18], 'message_deleted': r[19],
            })
        conn.commit()
        return rows
    finally:
        if cursor: cursor.close()
        conn.close()


def set_sticky_state(sticky_id, user_id, *, hidden=None, archived=None):
    conn = get_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor(); _ensure_stickies_table(cursor)
        updates, params = [], []
        if hidden is not None: updates.append('is_hidden=%s'); params.append(hidden)
        if archived is not None: updates.append('is_archived=%s'); params.append(archived)
        if not updates: return True
        params.extend([sticky_id, user_id])
        cursor.execute(f"UPDATE stickies SET {', '.join(updates)}, updated_at=CURRENT_TIMESTAMP WHERE id=%s AND user_id=%s", params)
        conn.commit(); return cursor.rowcount > 0
    finally:
        if cursor: cursor.close()
        conn.close()


def _archive_source_stickies(cursor, source_type, source_id):
    _ensure_stickies_table(cursor)
    cursor.execute("""UPDATE stickies SET is_archived=TRUE, is_hidden=FALSE,
        updated_at=CURRENT_TIMESTAMP WHERE source_type=%s AND source_id=%s AND is_archived=FALSE""",
        (source_type, source_id))


def _hide_archived_source_windows(source_type, source_id):
    try:
        from sticky_notes import hide_source_stickies
        hide_source_stickies(source_type, source_id)
    except (ImportError, RuntimeError):
        pass


def delete_sticky(sticky_id, user_id):
    conn = get_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        _ensure_stickies_table(cursor)
        cursor.execute("DELETE FROM stickies WHERE id=%s AND user_id=%s", (sticky_id, user_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        if cursor: cursor.close()
        conn.close()


def _ensure_pinned_chats_table(cursor):
    cursor.execute("""CREATE TABLE IF NOT EXISTS pinned_chats (
        user_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
        chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
        pinned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, chat_id))""")


def pin_chat(user_id, chat_id):
    return _set_chat_pin(user_id, chat_id, True)


def unpin_chat(user_id, chat_id):
    return _set_chat_pin(user_id, chat_id, False)


def _set_chat_pin(user_id, chat_id, pinned):
    conn = get_connection()
    if not conn:
        return False
    cursor = None
    try:
        cursor = conn.cursor()
        _ensure_pinned_chats_table(cursor)
        if pinned:
            cursor.execute("""INSERT INTO pinned_chats (user_id, chat_id)
                SELECT %s, chat_id FROM chat_members
                WHERE chat_id = %s AND employee_id = %s
                ON CONFLICT (user_id, chat_id) DO NOTHING""", (user_id, chat_id, user_id))
        else:
            cursor.execute("DELETE FROM pinned_chats WHERE user_id = %s AND chat_id = %s", (user_id, chat_id))
        changed = cursor.rowcount > 0
        conn.commit()
        return changed
    except Exception as error:
        conn.rollback()
        print(f"Ошибка изменения закрепления чата: {error}")
        return False
    finally:
        if cursor:
            cursor.close()
        conn.close()


def get_pinned_chats(user_id):
    conn = get_connection()
    if not conn:
        return set()
    cursor = None
    try:
        cursor = conn.cursor()
        _ensure_pinned_chats_table(cursor)
        cursor.execute("SELECT chat_id FROM pinned_chats WHERE user_id = %s", (user_id,))
        result = {row[0] for row in cursor.fetchall()}
        conn.commit()
        return result
    except Exception as error:
        conn.rollback()
        print(f"Ошибка получения закреплённых чатов: {error}")
        return set()
    finally:
        if cursor:
            cursor.close()
        conn.close()


def _ensure_drafts_table(cursor):
    cursor.execute("""CREATE TABLE IF NOT EXISTS drafts (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
        chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
        text TEXT NOT NULL DEFAULT '',
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (user_id, chat_id)
    )""")


def save_draft(user_id, chat_id, text):
    if not user_id or not chat_id:
        return False
    text = text or ""
    conn = get_connection()
    if not conn:
        return False
    cursor = None
    try:
        cursor = conn.cursor()
        _ensure_drafts_table(cursor)
        if text.strip():
            cursor.execute(
                """INSERT INTO drafts (user_id, chat_id, text, updated_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id, chat_id)
                DO UPDATE SET text = EXCLUDED.text, updated_at = CURRENT_TIMESTAMP""",
                (user_id, chat_id, text),
            )
        else:
            cursor.execute("DELETE FROM drafts WHERE user_id = %s AND chat_id = %s", (user_id, chat_id))
        conn.commit()
        return True
    except Exception as error:
        conn.rollback()
        print(f"Ошибка сохранения черновика: {error}")
        return False
    finally:
        if cursor:
            cursor.close()
        conn.close()


def get_draft(user_id, chat_id):
    if not user_id or not chat_id:
        return ""
    conn = get_connection()
    if not conn:
        return ""
    cursor = None
    try:
        cursor = conn.cursor()
        _ensure_drafts_table(cursor)
        cursor.execute("SELECT text FROM drafts WHERE user_id = %s AND chat_id = %s", (user_id, chat_id))
        row = cursor.fetchone()
        conn.commit()
        return row[0] if row else ""
    except Exception as error:
        conn.rollback()
        print(f"Ошибка получения черновика: {error}")
        return ""
    finally:
        if cursor:
            cursor.close()
        conn.close()


def delete_draft(user_id, chat_id):
    if not user_id or not chat_id:
        return False
    conn = get_connection()
    if not conn:
        return False
    cursor = None
    try:
        cursor = conn.cursor()
        _ensure_drafts_table(cursor)
        cursor.execute("DELETE FROM drafts WHERE user_id = %s AND chat_id = %s", (user_id, chat_id))
        conn.commit()
        return True
    except Exception as error:
        conn.rollback()
        print(f"Ошибка удаления черновика: {error}")
        return False
    finally:
        if cursor:
            cursor.close()
        conn.close()


def _ensure_image_attachments_table(cursor):
    cursor.execute("CREATE TABLE IF NOT EXISTS image_attachments (id SERIAL PRIMARY KEY, owner_type VARCHAR(20) NOT NULL, owner_id INTEGER NOT NULL, image_data BYTEA NOT NULL, file_name VARCHAR(255) NOT NULL DEFAULT 'screenshot.png', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_image_attachments_owner ON image_attachments(owner_type, owner_id)")


def _ensure_tasks_short_description_column(cursor):
    cursor.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS short_description TEXT")


def _save_image_attachments(cursor, owner_type, owner_id, images):
    if not images:
        return
    _ensure_image_attachments_table(cursor)
    for number, image in enumerate(images, start=1):
        cursor.execute("INSERT INTO image_attachments (owner_type, owner_id, image_data, file_name) VALUES (%s, %s, %s, %s)", (owner_type, owner_id, Binary(image), f"screenshot_{number}.png"))


def get_image_attachments(owner_type, owner_id):
    conn = get_connection()
    if not conn:
        return []
    cursor = None
    try:
        cursor = conn.cursor()
        _ensure_image_attachments_table(cursor)
        conn.commit()
        cursor.execute("SELECT image_data FROM image_attachments WHERE owner_type = %s AND owner_id = %s ORDER BY id", (owner_type, owner_id))
        return [bytes(row[0]) for row in cursor.fetchall()]
    except Exception as error:
        print(f"Failed to load screenshots: {error}")
        return []
    finally:
        if cursor:
            cursor.close()
        conn.close()


def get_message_attachments(message_ids):
    """Return message attachments in one query instead of one connection per bubble."""
    if not message_ids:
        return {}
    conn = get_connection()
    if not conn:
        return {}
    cursor = None
    try:
        cursor = conn.cursor()
        _ensure_image_attachments_table(cursor)
        cursor.execute(
            "SELECT owner_id, image_data FROM image_attachments "
            "WHERE owner_type = 'message' AND owner_id = ANY(%s) ORDER BY id",
            (list(message_ids),),
        )
        result = {}
        for message_id, image in cursor.fetchall():
            result.setdefault(message_id, []).append(bytes(image))
        return result
    except Exception as error:
        print(f"Failed to load message screenshots: {error}")
        return {}
    finally:
        if cursor:
            cursor.close()
        conn.close()


def add_image_attachments(owner_type, owner_id, images):
    if not images:
        return True
    conn = get_connection()
    if not conn:
        return False
    cursor = None
    try:
        cursor = conn.cursor()
        _save_image_attachments(cursor, owner_type, owner_id, images)
        conn.commit()
        return True
    except Exception as error:
        conn.rollback()
        print(f"Failed to save screenshots: {error}")
        return False
    finally:
        if cursor:
            cursor.close()
        conn.close()


def get_connection():
    """Получить подключение к БД."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"Ошибка подключения: {e}")
        return None


def check_connection():
    """
    Проверить подключение к базе данных.
    Возвращает True и сообщение при успехе,
    иначе False и текст ошибки.
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return True, "Подключение успешно"
    except Exception as e:
        return False, str(e)


def check_user(login, password):
    """
    Проверить логин и пароль пользователя.
    Пароль сравнивается через bcrypt.
    """
    import bcrypt

    conn = get_connection()
    if not conn:
        return False, "Ошибка подключения к базе данных"

    try:
        cursor = conn.cursor()

        cursor.execute("""
                       SELECT a.id,
                              a.password_hash,
                              a.is_locked,
                              e.id as employee_id,
                              e.last_name,
                              e.first_name,
                              e.middle_name,
                              e.email,
                              e.is_dismissed
                       FROM accounts a
                                JOIN employees e ON a.employee_id = e.id
                       WHERE a.login = %s
                       """, (login,))

        result = cursor.fetchone()

        if not result:
            return False, "Неверный логин или пароль"

        (account_id, password_hash, is_locked, emp_id,
         last_name, first_name, middle_name, email, is_dismissed) = result

        if is_locked:
            return False, "Учетная запись заблокирована"

        if is_dismissed:
            return False, "Сотрудник уволен"

        # Проверяем пароль через bcrypt
        if not bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
            return False, "Неверный логин или пароль"

        user_data = {
            'account_id': account_id,
            'employee_id': emp_id,
            'last_name': last_name,
            'first_name': first_name,
            'middle_name': middle_name,
            'email': email,
            'full_name': f"{last_name} {first_name} {middle_name or ''}".strip()
        }

        return True, user_data

    except Exception as e:
        return False, f"Ошибка: {str(e)}"
    finally:
        cursor.close()
        conn.close()


def register_user(last_name, first_name, middle_name, birth_date,
                  start_date, position_id, department_id, email,
                  login, password):
    """
    Зарегистрировать нового пользователя.
    Пароль хешируется через bcrypt.
    """
    import bcrypt

    conn = get_connection()
    if not conn:
        return False, "Ошибка подключения к базе данных"

    try:
        cursor = conn.cursor()

        # Проверяем, существует ли уже такой логин
        cursor.execute("SELECT id FROM accounts WHERE login = %s", (login,))
        if cursor.fetchone():
            return False, "Логин уже занят"

        # Проверяем, существует ли уже такая почта
        cursor.execute("SELECT id FROM employees WHERE email = %s", (email,))
        if cursor.fetchone():
            return False, "Email уже используется"

        # Хешируем пароль
        password_hash = bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt()
        ).decode('utf-8')

        # Создаём сотрудника
        cursor.execute("""
                       INSERT INTO employees (last_name, first_name, middle_name,
                                              birth_date, start_date, position_id,
                                              department_id, email)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                       """, (last_name, first_name, middle_name, birth_date,
                             start_date, position_id, department_id, email))

        employee_id = cursor.fetchone()[0]

        # Создаём учётную запись с хешем пароля
        cursor.execute("""
                       INSERT INTO accounts (login, password_hash, employee_id)
                       VALUES (%s, %s, %s)
                       """, (login, password_hash, employee_id))

        conn.commit()
        return True, "Регистрация успешна"

    except Exception as e:
        conn.rollback()
        return False, f"Ошибка: {str(e)}"
    finally:
        cursor.close()
        conn.close()


def get_positions():
    """Получить список должностей."""
    conn = get_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title FROM positions ORDER BY id")
        return cursor.fetchall()
    except Exception as e:
        print(f"Ошибка: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_departments():
    """Получить список отделов."""
    conn = get_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title FROM departments ORDER BY id")
        return cursor.fetchall()
    except Exception as e:
        print(f"Ошибка: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_employees(search_query=None):
    """
    Получить список сотрудников.
    Если search_query передан — фильтр по ФИО (без учёта регистра).
    Возвращает список кортежей (id, last_name, first_name, middle_name).
    """
    conn = get_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()

        if search_query:
            query = """
                    SELECT id, last_name, first_name, middle_name
                    FROM employees
                    WHERE is_dismissed = FALSE
                      AND (
                        LOWER(last_name) LIKE LOWER(%s) OR
                        LOWER(first_name) LIKE LOWER(%s) OR
                        LOWER(middle_name) LIKE LOWER(%s)
                        )
                    ORDER BY last_name, first_name
                    """
            search_param = f"%{search_query}%"
            cursor.execute(query, (search_param, search_param, search_param))
        else:
            cursor.execute("""
                           SELECT id, last_name, first_name, middle_name
                           FROM employees
                           WHERE is_dismissed = FALSE
                           ORDER BY last_name, first_name
                           """)

        return cursor.fetchall()
    except Exception as e:
        print(f"Ошибка получения сотрудников: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

def create_group_chat(name, creator_id, member_ids):
    """
    Создать групповой чат.
    member_ids — список id сотрудников (включая создателя).
    Возвращает chat_id или None при ошибке.
    """
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chats (name, is_group, created_by) VALUES (%s, TRUE, %s) RETURNING id",
            (name, creator_id)
        )
        chat_id = cursor.fetchone()[0]
        # Добавляем участников
        for emp_id in member_ids:
            cursor.execute(
                "INSERT INTO chat_members (chat_id, employee_id) VALUES (%s, %s) ON CONFLICT (chat_id, employee_id) DO NOTHING",
                (chat_id, emp_id)
            )
        conn.commit()
        return chat_id
    except Exception as e:
        conn.rollback()
        print(f"Ошибка создания чата: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def get_or_create_personal_chat(user_id, contact_id):
    """
    Найти существующий личный чат между двумя сотрудниками или создать новый.
    Возвращает chat_id.
    """
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        # Ищем личный чат, где оба участника
        cursor.execute("""
            SELECT cm1.chat_id
            FROM chat_members cm1
            JOIN chat_members cm2 ON cm1.chat_id = cm2.chat_id
            JOIN chats c ON cm1.chat_id = c.id
            WHERE cm1.employee_id = %s AND cm2.employee_id = %s
              AND c.is_group = FALSE
            LIMIT 1
        """, (user_id, contact_id))
        row = cursor.fetchone()
        if row:
            return row[0]
        # Создаём новый личный чат
        cursor.execute(
            "INSERT INTO chats (is_group) VALUES (FALSE) RETURNING id"
        )
        chat_id = cursor.fetchone()[0]
        cursor.execute(
            "INSERT INTO chat_members (chat_id, employee_id) VALUES (%s, %s), (%s, %s)",
            (chat_id, user_id, chat_id, contact_id)
        )
        conn.commit()
        return chat_id
    except Exception as e:
        conn.rollback()
        print(f"Ошибка получения чата: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def get_user_chats(user_id):
    """
    Получить список чатов пользователя с последним сообщением и непрочитанными (для текущего пользователя).
    Возвращает список словарей:
    {chat_id, name, is_group, last_message, last_time, unread_count}
    """
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                c.id,
                c.name,
                c.is_group,
                (SELECT m.message_text FROM messages m WHERE m.chat_id = c.id ORDER BY m.created_at DESC LIMIT 1) as last_message,
                (SELECT m.created_at FROM messages m WHERE m.chat_id = c.id ORDER BY m.created_at DESC LIMIT 1) as last_time,
                -- непрочитанные (заглушка, пока не реализована отметка прочтения; считаем все сообщения)
                0 as unread_count
            FROM chats c
            JOIN chat_members cm ON c.id = cm.chat_id
            WHERE cm.employee_id = %s
            ORDER BY last_time DESC NULLS LAST
        """, (user_id,))
        chats = []
        for row in cursor.fetchall():
            chats.append({
                'chat_id': row[0],
                'name': row[1],
                'is_group': row[2],
                'last_message': row[3] or "Нет сообщений",
                'last_time': row[4],
                'unread_count': row[5] or 0
            })
        return chats
    except Exception as e:
        print(f"Ошибка получения чатов: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_chat_messages(chat_id, limit=50, offset=0, order_desc=False):
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        order_direction = "DESC" if order_desc else "ASC"
        query = """
            SELECT m.id, m.sender_id,
                   e.last_name || ' ' || e.first_name as sender_name,
                   m.message_text, m.created_at, m.is_read, m.is_deleted, m.edited_at,
                   m.is_forwarded, m.forwarded_from, m.forwarded_at
            FROM messages m
            JOIN employees e ON m.sender_id = e.id
            WHERE m.chat_id = %s
            ORDER BY m.created_at {}
            LIMIT %s OFFSET %s
        """.format(order_direction)   # <-- безопасно, т.к. order_direction жёстко задан (DESC/ASC)
        cursor.execute(query, (chat_id, limit, offset))
        messages = []
        for row in cursor.fetchall():
            messages.append({
                'id': row[0],
                'sender_id': row[1],
                'sender_name': row[2],
                'text': row[3],
                'created_at': row[4],
                'time': row[4].strftime("%H:%M") if row[4] else "",
                'is_read': row[5],
                'is_deleted': row[6],
                'edited_at': row[7].strftime("%H:%M") if row[7] else None,
                'is_forwarded': row[8],
                'forwarded_from': row[9],
                'forwarded_at': row[10].strftime("%H:%M") if row[10] else None
            })
        return list(reversed(messages)) if order_desc else messages
    except Exception as e:
        print(f"Ошибка получения сообщений: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def search_chat_messages(chat_id, query, limit=500):
    """Search a chat by message text or a date written as DD.MM or DD.MM.YYYY."""
    query = (query or "").strip()
    if not query:
        return get_chat_messages(chat_id, limit=limit)
    conn = get_connection()
    if not conn:
        return []
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.id, m.sender_id, e.last_name || ' ' || e.first_name,
                   m.message_text, m.created_at, m.is_read, m.is_deleted, m.edited_at,
                   m.is_forwarded, m.forwarded_from, m.forwarded_at
            FROM messages m
            JOIN employees e ON m.sender_id = e.id
            WHERE m.chat_id = %s
              AND (m.message_text ILIKE %s
                   OR to_char(m.created_at, 'DD.MM.YYYY') ILIKE %s
                   OR to_char(m.created_at, 'DD.MM') ILIKE %s)
            ORDER BY m.created_at ASC
            LIMIT %s
        """, (chat_id, f"%{query}%", f"%{query}%", f"%{query}%", limit))
        return [{
            'id': row[0], 'sender_id': row[1], 'sender_name': row[2],
            'text': row[3], 'created_at': row[4],
            'time': row[4].strftime('%H:%M') if row[4] else '',
            'is_read': row[5], 'is_deleted': row[6],
            'edited_at': row[7].strftime('%H:%M') if row[7] else None,
            'is_forwarded': row[8], 'forwarded_from': row[9],
            'forwarded_at': row[10].strftime('%H:%M') if row[10] else None,
        } for row in cursor.fetchall()]
    except Exception as error:
        print(f"Ошибка поиска сообщений: {error}")
        return []
    finally:
        if cursor:
            cursor.close()
        conn.close()


def send_message(chat_id, sender_id, text, images=None):
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (chat_id, sender_id, message_text) VALUES (%s, %s, %s) RETURNING id",
            (chat_id, sender_id, text)
        )
        message_id = cursor.fetchone()[0]
        _save_image_attachments(cursor, 'message', message_id, images)
        conn.commit()

        # Notify every other member.  This applies to groups as well as personal chats.
        cursor.execute("""
                       SELECT cm.employee_id
                       FROM chat_members cm
                       WHERE cm.chat_id = %s AND cm.employee_id != %s
                       """, (chat_id, sender_id))
        receivers = [row[0] for row in cursor.fetchall()]
        if receivers:
            cursor.execute("SELECT last_name, first_name FROM employees WHERE id = %s", (sender_id,))
            sender_info = cursor.fetchone()
            sender_name = f"{sender_info[0]} {sender_info[1]}" if sender_info else "Пользователь"
            preview = text[:50] if text else "📎 Вложение"
            for receiver_id in receivers:
                create_notification(receiver_id, chat_id, message_id,
                                    f"Новое сообщение от {sender_name}: {preview}")
        return True
    except Exception as e:
        conn.rollback()
        print(f"Ошибка отправки: {e}")
        return False
    finally:
        cursor.close()
        conn.close()



def get_or_create_self_chat(user_id):
    """
    Получить или создать чат с самим собой (Избранное).
    Возвращает chat_id.
    """
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        # Ищем существующий чат с is_self = TRUE, где участник только этот пользователь
        cursor.execute("""
            SELECT c.id FROM chats c
            JOIN chat_members cm ON c.id = cm.chat_id
            WHERE c.is_self = TRUE AND cm.employee_id = %s
            LIMIT 1
        """, (user_id,))
        row = cursor.fetchone()
        if row:
            return row[0]
        # Создаём
        cursor.execute("INSERT INTO chats (is_self) VALUES (TRUE) RETURNING id")
        chat_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO chat_members (chat_id, employee_id) VALUES (%s, %s)", (chat_id, user_id))
        conn.commit()
        return chat_id
    except Exception as e:
        conn.rollback()
        print(f"Ошибка создания избранного: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def get_contacts_and_groups(user_id, search_query=None):
    """
    Получить объединённый список сотрудников и групповых чатов.
    Возвращает список словарей:
    [
        {'type': 'employee', 'id': emp_id, 'name': 'ФИО', 'chat_id': None},
        {'type': 'group', 'id': chat_id, 'name': 'Название группы', 'chat_id': chat_id},
        {'type': 'self', 'id': None, 'name': 'Избранное', 'chat_id': self_chat_id}
    ]
    """
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        results = []

        # Чат "Избранное" (с самим собой)
        self_chat_id = get_or_create_self_chat(user_id)
        if self_chat_id:
            results.append({'type': 'self', 'id': None, 'name': 'Избранное', 'chat_id': self_chat_id})

        # Сотрудники (кроме себя)
        emp_query = """
            SELECT id, last_name, first_name, middle_name
            FROM employees
            WHERE is_dismissed = FALSE AND id != %s
        """
        params = [user_id]
        if search_query:
            emp_query += """ AND (
                LOWER(last_name) LIKE LOWER(%s) OR
                LOWER(first_name) LIKE LOWER(%s) OR
                LOWER(middle_name) LIKE LOWER(%s)
            )"""
            like_str = f"%{search_query}%"
            params.extend([like_str, like_str, like_str])
        emp_query += " ORDER BY last_name, first_name"
        cursor.execute(emp_query, params)
        for row in cursor.fetchall():
            emp_id, last_name, first_name, middle_name = row
            full_name = f"{last_name} {first_name}"
            if middle_name:
                full_name += f" {middle_name}"
            results.append({'type': 'employee', 'id': emp_id, 'name': full_name, 'chat_id': None})

        # Групповые чаты, где пользователь участник
        group_query = """
            SELECT c.id, c.name, c.created_by
            FROM chats c
            JOIN chat_members cm ON c.id = cm.chat_id
            WHERE c.is_group = TRUE AND cm.employee_id = %s
        """
        gparams = [user_id]
        if search_query:
            group_query += " AND LOWER(c.name) LIKE LOWER(%s)"
            gparams.append(f"%{search_query}%")
        group_query += " ORDER BY c.name"
        cursor.execute(group_query, gparams)
        for row in cursor.fetchall():
            chat_id, name, created_by = row
            results.append({'type': 'group', 'id': chat_id, 'name': name, 'chat_id': chat_id, 'created_by': created_by})

        return results
    except Exception as e:
        print(f"Ошибка получения контактов: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


# Изменённая функция создания группового чата (без запроса имени)
def create_group_chat_auto(user_id, member_ids):
    """
    Создать групповой чат с автоназванием "Группа №{chat_id}".
    Возвращает chat_id и name или (None, None) при ошибке.
    """
    conn = get_connection()
    if not conn:
        return None, None
    try:
        cursor = conn.cursor()
        # Создаём чат
        cursor.execute(
            "INSERT INTO chats (is_group, created_by) VALUES (TRUE, %s) RETURNING id",
            (user_id,)
        )
        chat_id = cursor.fetchone()[0]
        # Автоназвание
        auto_name = f"Группа №{chat_id}"
        cursor.execute("UPDATE chats SET name = %s WHERE id = %s", (auto_name, chat_id))
        # Добавляем участников
        for emp_id in member_ids:
            cursor.execute(
                "INSERT INTO chat_members (chat_id, employee_id) VALUES (%s, %s) ON CONFLICT (chat_id, employee_id) DO NOTHING",
                (chat_id, emp_id)
            )
        conn.commit()
        return chat_id, auto_name
    except Exception as e:
        conn.rollback()
        print(f"Ошибка создания группы: {e}")
        return None, None
    finally:
        cursor.close()
        conn.close()


def delete_group_chat(chat_id, user_id):
    """
    Удалить групповой чат. Может только создатель (created_by).
    Возвращает True при успехе.
    """
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        # Проверяем, что пользователь является создателем
        cursor.execute("SELECT created_by FROM chats WHERE id = %s AND is_group = TRUE", (chat_id,))
        row = cursor.fetchone()
        if not row or row[0] != user_id:
            return False
        # Удаляем участников
        cursor.execute("DELETE FROM chat_members WHERE chat_id = %s", (chat_id,))
        # Удаляем сообщения
        cursor.execute("DELETE FROM messages WHERE chat_id = %s", (chat_id,))
        # Удаляем уведомления
        cursor.execute("DELETE FROM notifications WHERE chat_id = %s", (chat_id,))
        # Удаляем чат
        cursor.execute("DELETE FROM chats WHERE id = %s", (chat_id,))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Ошибка удаления группы: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def mark_messages_as_read(chat_id, user_id):
    """
    Пометить все входящие сообщения в чате как прочитанные.
    (сообщения, отправленные не user_id)
    """
    conn = get_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE messages
            SET is_read = TRUE
            WHERE chat_id = %s
              AND sender_id != %s
              AND is_read = FALSE
        """, (chat_id, user_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Ошибка mark_messages_as_read: {e}")
    finally:
        cursor.close()
        conn.close()

def edit_message(message_id, new_text, sender_id=None):
    """Редактировать сообщение. Возвращает True/False."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        query = "UPDATE messages SET message_text = %s, edited_at = NOW() WHERE id = %s AND is_deleted = FALSE"
        params = [new_text, message_id]
        if sender_id is not None:
            query += " AND sender_id = %s"
            params.append(sender_id)
        cursor.execute(query, params)
        conn.commit()
        return cursor.rowcount == 1
    except Exception as e:
        conn.rollback()
        print(f"Ошибка редактирования: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def delete_message(message_id, sender_id=None):
    """Полное удаление сообщения."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        query = "SELECT id FROM messages WHERE id = %s FOR UPDATE"
        params = [message_id]
        if sender_id is not None:
            query = "SELECT id FROM messages WHERE id = %s AND sender_id = %s FOR UPDATE"
            params.append(sender_id)
        cursor.execute(query, params)
        if not cursor.fetchone():
            conn.rollback()
            return False
        _archive_source_stickies(cursor, 'message', message_id)
        # Remove dependent rows first, then the message itself (hard delete).
        cursor.execute("DELETE FROM notifications WHERE message_id = %s", (message_id,))
        cursor.execute("DELETE FROM image_attachments WHERE owner_type = 'message' AND owner_id = %s", (message_id,))
        cursor.execute("DELETE FROM messages WHERE id = %s", (message_id,))
        conn.commit()
        _hide_archived_source_windows('message', message_id)
        return True
    except Exception as e:
        conn.rollback()
        print(f"Ошибка удаления сообщения: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def create_notification(user_id, chat_id, message_id, text, n_type='new_message'):
    """
    Создать уведомление для пользователя.
    Возвращает True при успехе.
    """
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
                       INSERT INTO notifications (user_id, chat_id, message_id, type, text)
                       VALUES (%s, %s, %s, %s, %s)
                       """, (user_id, chat_id, message_id, n_type, text))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Ошибка создания уведомления: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def get_notifications(user_id, limit=20, unread_only=False):
    """
    Получить уведомления пользователя.
    Возвращает список словарей.
    """
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        query = """
                SELECT n.id, \
                       n.chat_id, \
                       n.message_id, \
                       n.type, \
                       n.text, \
                       n.is_read,
                       to_char(n.created_at, 'DD.MM HH24:MI') as created_at
                FROM notifications n
                WHERE n.user_id = %s \
                """
        params = [user_id]
        if unread_only:
            query += " AND n.is_read = FALSE"
        query += " ORDER BY n.created_at DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        notifications = []
        for row in cursor.fetchall():
            notifications.append({
                'id': row[0],
                'chat_id': row[1],
                'message_id': row[2],
                'type': row[3],
                'text': row[4],
                'is_read': row[5],
                'created_at': row[6]
            })
        return notifications
    except Exception as e:
        print(f"Ошибка получения уведомлений: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_unread_notification_count(user_id):
    """Количество непрочитанных уведомлений."""
    conn = get_connection()
    if not conn:
        return 0
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id = %s AND is_read = FALSE",
            (user_id,)
        )
        return cursor.fetchone()[0]
    except Exception as e:
        print(f"Ошибка подсчёта уведомлений: {e}")
        return 0
    finally:
        cursor.close()
        conn.close()


def mark_notifications_as_read(user_id, chat_id=None):
    """
    Отметить уведомления прочитанными. Если chat_id передан – только для этого чата.
    """
    conn = get_connection()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        if chat_id:
            cursor.execute("""
                           UPDATE notifications
                           SET is_read = TRUE
                           WHERE user_id = %s
                             AND chat_id = %s
                             AND is_read = FALSE
                           """, (user_id, chat_id))
        else:
            cursor.execute("""
                           UPDATE notifications
                           SET is_read = TRUE
                           WHERE user_id = %s
                             AND is_read = FALSE
                           """, (user_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Ошибка отметки уведомлений: {e}")
    finally:
        cursor.close()
        conn.close()

def get_personal_chats(user_id):
    """
    Возвращает словарь {собеседник_id: chat_id} для всех личных чатов пользователя.
    """
    conn = get_connection()
    if not conn:
        return {}
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT cm2.employee_id, c.id
            FROM chats c
            JOIN chat_members cm1 ON c.id = cm1.chat_id AND cm1.employee_id = %s
            JOIN chat_members cm2 ON c.id = cm2.chat_id AND cm2.employee_id != %s
            WHERE c.is_group = FALSE
        """, (user_id, user_id))
        return {row[0]: row[1] for row in cursor.fetchall()}
    except Exception as e:
        print(f"Ошибка получения личных чатов: {e}")
        return {}
    finally:
        cursor.close()
        conn.close()

def get_unread_message_counts(user_id):
    """
    Возвращает словарь {chat_id: количество_непрочитанных} для всех чатов пользователя.
    Непрочитанными считаются сообщения, где is_read = FALSE и sender_id != user_id.
    """
    conn = get_connection()
    if not conn:
        return {}
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.chat_id, COUNT(*)
            FROM messages m
            JOIN chat_members cm ON m.chat_id = cm.chat_id AND cm.employee_id = %s
            WHERE m.sender_id != %s AND m.is_read = FALSE
            GROUP BY m.chat_id
        """, (user_id, user_id))
        return {row[0]: row[1] for row in cursor.fetchall()}
    except Exception as e:
        print(f"Ошибка получения непрочитанных: {e}")
        return {}
    finally:
        cursor.close()
        conn.close()

def get_new_messages(chat_id, last_id):
    """Получить сообщения с id > last_id для чата."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.id, m.sender_id, e.last_name || ' ' || e.first_name as sender_name,
                   m.message_text, m.created_at, m.is_read, m.is_deleted, m.edited_at,
                   m.is_forwarded, m.forwarded_from, m.forwarded_at
            FROM messages m
            JOIN employees e ON m.sender_id = e.id
            WHERE m.chat_id = %s AND m.id > %s
            ORDER BY m.id ASC
        """, (chat_id, last_id))
        messages = []
        for row in cursor.fetchall():
            messages.append({
                'id': row[0],
                'sender_id': row[1],
                'sender_name': row[2],
                'text': row[3],
                'created_at': row[4],
                'time': row[4].strftime("%H:%M") if row[4] else "",
                'is_read': row[5],
                'is_deleted': row[6],
                'edited_at': row[7].strftime("%H:%M") if row[7] else None,
                'is_forwarded': row[8],
                'forwarded_from': row[9],
                'forwarded_at': row[10].strftime("%H:%M") if row[10] else None
            })
        return messages
    except Exception as e:
        print(f"Ошибка получения новых сообщений: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def forward_messages(target_chat_id, sender_id, messages_to_forward):
    """
    Переслать сообщения в другой чат.
    messages_to_forward - список словарей с ключами: id, text, sender_name, time
    Возвращает True при успехе.
    """
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        _ensure_image_attachments_table(cursor)
        
        # Получаем информацию о текущем пользователе для отображения
        cursor.execute("SELECT last_name, first_name FROM employees WHERE id = %s", (sender_id,))
        user_info = cursor.fetchone()
        forwarder_name = f"{user_info[0]} {user_info[1]}" if user_info else "Неизвестно"
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        for msg in messages_to_forward:
            # Формируем текст пересланного сообщения
            original_sender = msg.get('sender_name', 'Неизвестно')
            original_time = msg.get('time', '')
            original_text = msg.get('text', '')
            
            # Текст пересланного сообщения с информацией об оригинале
            forwarded_text = f"----------\nПереслано от {original_sender} ({original_time})\n{original_text}"
            
            # Вставляем сообщение в целевой чат
            cursor.execute(
                "INSERT INTO messages (chat_id, sender_id, message_text, is_forwarded, forwarded_from, forwarded_at) "
                "VALUES (%s, %s, %s, TRUE, %s, %s) RETURNING id",
                (target_chat_id, sender_id, forwarded_text, original_sender, current_time)
            )
            forwarded_message_id = cursor.fetchone()[0]
            # Copy every screenshot in the same transaction as the forwarded message.
            cursor.execute(
                "SELECT image_data FROM image_attachments WHERE owner_type = 'message' AND owner_id = %s ORDER BY id",
                (msg['id'],),
            )
            images = [bytes(row[0]) for row in cursor.fetchall()]
            _save_image_attachments(cursor, 'message', forwarded_message_id, images)
        
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Ошибка пересылки сообщений: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

# ==================== ФУНКЦИИ ДЛЯ ЗАДАЧ ====================

def get_all_employees_for_selector():
    """Получить всех активных сотрудников для селекторов."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, last_name, first_name, middle_name, email
            FROM employees
            WHERE is_dismissed = FALSE
            ORDER BY last_name, first_name
        """)
        results = []
        for row in cursor.fetchall():
            full_name = f"{row[1]} {row[2]} {row[3] or ''}".strip()
            results.append({'id': row[0], 'name': full_name, 'email': row[4]})
        return results
    except Exception as e:
        print(f"Ошибка получения сотрудников: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_all_tags():
    """Получить все существующие теги."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, color FROM task_tags ORDER BY name")
        return cursor.fetchall()
    except Exception as e:
        print(f"Ошибка получения тегов: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_all_statuses():
    """Получить все статусы задач."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, code, title, color, sort_order FROM task_statuses ORDER BY sort_order")
        return cursor.fetchall()
    except Exception as e:
        print(f"Ошибка получения статусов: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_all_priorities():
    """Получить все приоритеты задач."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, code, title, color, sort_order FROM task_priorities ORDER BY sort_order")
        return cursor.fetchall()
    except Exception as e:
        print(f"Ошибка получения приоритетов: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_status_by_code(code):
    """Получить статус по коду."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, code, title, color FROM task_statuses WHERE code = %s", (code,))
        return cursor.fetchone()
    except Exception as e:
        print(f"Ошибка получения статуса: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def get_priority_by_code(code):
    """Получить приоритет по коду."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, code, title, color FROM task_priorities WHERE code = %s", (code,))
        return cursor.fetchone()
    except Exception as e:
        print(f"Ошибка получения приоритета: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def create_tag(name, color="#808080"):
    """Создать новый тег."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO task_tags (name, color) VALUES (%s, %s) ON CONFLICT (name) DO UPDATE SET color = %s RETURNING id",
            (name, color, color)
        )
        tag_id = cursor.fetchone()[0]
        conn.commit()
        return tag_id
    except Exception as e:
        conn.rollback()
        print(f"Ошибка создания тега: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def create_task(title, description, author_id, executor_id, observers_ids, deadline, priority, tag_ids, creator_id, status_id=None, priority_id=None, images=None, short_description=None):
    """Создать новую задачу."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        _ensure_tasks_short_description_column(cursor)
        # Создаем задачу - поддерживаем как старый формат (priority как текст), так и новый (priority_id)
        if priority_id is not None:
            cursor.execute("""
                INSERT INTO tasks (title, short_description, description, author_id, executor_id, deadline, priority_id, created_by, status_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (title, short_description, description, author_id, executor_id, deadline, priority_id, creator_id, status_id))
        else:
            cursor.execute("""
                INSERT INTO tasks (title, short_description, description, author_id, executor_id, deadline, priority, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (title, short_description, description, author_id, executor_id, deadline, priority, creator_id))
        task_id = cursor.fetchone()[0]
        _save_image_attachments(cursor, 'task', task_id, images)

        priority_name = priority or ''
        if priority_id is not None:
            cursor.execute("SELECT title, code FROM task_priorities WHERE id=%s", (priority_id,))
            priority_row = cursor.fetchone()
            if priority_row:
                priority_name = f"{priority_row[0]} {priority_row[1]}"
        normalized_priority = priority_name.strip().casefold()
        if (short_description or '').strip() and any(value in normalized_priority for value in ('критич', 'блокер', 'critical', 'blocker')):
            _ensure_stickies_table(cursor)
            cursor.execute("""INSERT INTO stickies
                (user_id, source_type, source_id, title, text, color, pin_mode)
                VALUES (%s, 'task', %s, %s, %s, '#fca5a5', 'top_locked')""",
                (executor_id, task_id, title or 'Задача', short_description.strip()))
        
        # Добавляем наблюдателей
        for obs_id in observers_ids:
            cursor.execute(
                "INSERT INTO task_observers (task_id, employee_id) VALUES (%s, %s)",
                (task_id, obs_id)
            )
        
        # Добавляем теги
        for tag_id in tag_ids:
            cursor.execute(
                "INSERT INTO task_tags_link (task_id, tag_id) VALUES (%s, %s)",
                (task_id, tag_id)
            )
        
        conn.commit()
        return task_id
    except Exception as e:
        conn.rollback()
        print(f"Ошибка создания задачи: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def update_task(task_id, title=None, description=None, executor_id=None, status=None, priority=None, deadline=None, observers_ids=None, tag_ids=None, status_id=None, priority_id=None, short_description=None):
    """Обновить задачу. Параметры могут быть None для частичного обновления."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        _ensure_tasks_short_description_column(cursor)
        
        # Если переданы status_id или priority_id, получаем соответствующие текстовые значения
        if status_id is not None:
            cursor.execute("SELECT title, code FROM task_statuses WHERE id = %s", (status_id,))
            result = cursor.fetchone()
            if result:
                status = result[0]
                status_code = result[1]
            else:
                status_code = None
        else:
            status_code = None
        
        if priority_id is not None:
            cursor.execute("SELECT title FROM task_priorities WHERE id = %s", (priority_id,))
            result = cursor.fetchone()
            if result:
                priority = result[0]
        
        # Формируем динамический SQL для частичного обновления
        updates = []
        params = []
        
        if title is not None:
            updates.append("title=%s")
            params.append(title)
        if short_description is not None:
            updates.append("short_description=%s")
            params.append(short_description)
        if description is not None:
            updates.append("description=%s")
            params.append(description)
        if executor_id is not None:
            updates.append("executor_id=%s")
            params.append(executor_id)
        # Поддерживаем как старый формат (status как текст), так и новый (status_id)
        if status is not None:
            updates.append("status=%s")
            params.append(status)
        if status_id is not None:
            updates.append("status_id=%s")
            params.append(status_id)
        # Поддерживаем как старый формат (priority как текст), так и новый (priority_id)
        if priority is not None:
            updates.append("priority=%s")
            params.append(priority)
        if priority_id is not None:
            updates.append("priority_id=%s")
            params.append(priority_id)
        if deadline is not None:
            updates.append("deadline=%s")
            params.append(deadline)
        
        if updates:
            updates.append("updated_at=CURRENT_TIMESTAMP")
            params.append(task_id)
            
            sql = f"UPDATE tasks SET {', '.join(updates)} WHERE id=%s"
            cursor.execute(sql, tuple(params))
        
        # Обновляем наблюдателей, если переданы
        if observers_ids is not None:
            cursor.execute("DELETE FROM task_observers WHERE task_id=%s", (task_id,))
            for obs_id in observers_ids:
                cursor.execute(
                    "INSERT INTO task_observers (task_id, employee_id) VALUES (%s, %s)",
                    (task_id, obs_id)
                )
        
        # Обновляем теги, если переданы
        if tag_ids is not None:
            cursor.execute("DELETE FROM task_tags_link WHERE task_id=%s", (task_id,))
            for tag_id in tag_ids:
                cursor.execute(
                    "INSERT INTO task_tags_link (task_id, tag_id) VALUES (%s, %s)",
                    (task_id, tag_id)
                )

        normalized_status = f"{status or ''} {status_code or ''}".strip().casefold()
        if any(value in normalized_status for value in ('выполн', 'заверш', 'done', 'completed')):
            _archive_source_stickies(cursor, 'task', task_id)
        
        conn.commit()
        if any(value in normalized_status for value in ('выполн', 'заверш', 'done', 'completed')):
            _hide_archived_source_windows('task', task_id)
        return True
    except Exception as e:
        conn.rollback()
        print(f"Ошибка обновления задачи: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def delete_task(task_id, user_id):
    """Удалить задачу.
    Пользователь может удалить только задачу, которую он создал.
    Возвращает True при успехе, False при ошибке или отсутствии прав.
    """
    conn = get_connection()
    if not conn:
        return False, "Ошибка подключения к базе данных"
    try:
        cursor = conn.cursor()
        
        # Проверяем, является ли пользователь автором задачи
        cursor.execute("SELECT author_id FROM tasks WHERE id = %s", (task_id,))
        result = cursor.fetchone()
        
        if not result:
            return False, "Задача не найдена"
        
        author_id = result[0]
        
        if author_id != user_id:
            return False, "Удалить задачу может только её автор"

        _archive_source_stickies(cursor, 'task', task_id)
        
        # Удаляем связанные записи
        cursor.execute("DELETE FROM task_observers WHERE task_id = %s", (task_id,))
        cursor.execute("DELETE FROM task_tags_link WHERE task_id = %s", (task_id,))
        
        # Удаляем саму задачу
        cursor.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
        
        conn.commit()
        _hide_archived_source_windows('task', task_id)
        return True, "Задача успешно удалена"
    except Exception as e:
        conn.rollback()
        print(f"Ошибка удаления задачи: {e}")
        return False, f"Ошибка: {str(e)}"
    finally:
        cursor.close()
        conn.close()


def get_tasks(filter_params=None, current_user_id=None, sort_by='created_at', sort_order='DESC'):
    """Получить список задач с фильтрацией.
    Если передан current_user_id, возвращаются задачи, где пользователь
    является автором, исполнителем или наблюдателем.
    
    sort_by: 'deadline', 'priority', 'created_at', 'updated_at'
    sort_order: 'ASC', 'DESC'
    """
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        _ensure_tasks_short_description_column(cursor)
        query = """
            SELECT 
                t.id,
                t.title,
                t.short_description,
                t.description,
                t.status,
                t.priority,
                t.deadline,
                t.created_at,
                a.last_name || ' ' || a.first_name as author_name,
                e.last_name || ' ' || e.first_name as executor_name,
                c.last_name || ' ' || c.first_name as creator_name,
                t.author_id
            FROM tasks t
            JOIN employees a ON t.author_id = a.id
            JOIN employees e ON t.executor_id = e.id
            JOIN employees c ON t.created_by = c.id
        """
        params = []
        
        # Если передан current_user_id, фильтруем по роли пользователя
        if current_user_id is not None:
            query += """
            WHERE (
                t.author_id = %s 
                OR t.executor_id = %s 
                OR EXISTS (
                    SELECT 1 FROM task_observers tobs 
                    WHERE tobs.task_id = t.id AND tobs.employee_id = %s
                )
            )
            """
            params.extend([current_user_id, current_user_id, current_user_id])
        
        # Дополнительные фильтры
        if filter_params:
            conditions = []
            if filter_params.get('status') is not None:
                conditions.append("t.status = %s")
                params.append(filter_params['status'])
            if filter_params.get('priority') is not None:
                conditions.append("t.priority = %s")
                params.append(filter_params['priority'])
            if filter_params.get('executor_id') is not None:
                conditions.append("t.executor_id = %s")
                params.append(filter_params['executor_id'])
            if filter_params.get('author_id') is not None:
                conditions.append("t.author_id = %s")
                params.append(filter_params['author_id'])
            
            # Поиск по названию, описанию и исполнителю
            if filter_params.get('search'):
                search_param = f"%{filter_params['search']}%"
                conditions.append("""(
                    LOWER(t.title) LIKE LOWER(%s) 
                    OR LOWER(COALESCE(t.description, '')) LIKE LOWER(%s) 
                    OR LOWER(e.last_name || ' ' || e.first_name) LIKE LOWER(%s)
                )""")
                params.extend([search_param, search_param, search_param])
            
            # Фильтр "Мои задачи" - только те, где пользователь исполнитель
            if filter_params.get('my_tasks_only') and current_user_id:
                conditions.append("t.executor_id = %s")
                params.append(current_user_id)
            
            if conditions:
                # Если уже есть WHERE для current_user_id, используем AND
                if current_user_id is not None:
                    query += " AND " + " AND ".join(conditions)
                else:
                    query += " WHERE " + " AND ".join(conditions)
        
        # Сортировка
        valid_sort_columns = ['deadline', 'priority', 'created_at', 'updated_at']
        if sort_by in valid_sort_columns:
            order_direction = 'ASC' if sort_order == 'ASC' else 'DESC'
            # Для приоритета используем CASE для правильной сортировки
            if sort_by == 'priority':
                query += f""" ORDER BY 
                    CASE t.priority
                        WHEN 'Блокер' THEN 4
                        WHEN 'Критичный' THEN 3
                        WHEN 'Средний' THEN 2
                        WHEN 'Низкий' THEN 1
                        ELSE 0
                    END {order_direction}"""
            else:
                query += f" ORDER BY t.{sort_by} {order_direction}"
        else:
            query += " ORDER BY t.created_at DESC"
        
        cursor.execute(query, params)
        tasks = []
        for row in cursor.fetchall():
            tasks.append({
                'id': row[0],
                'title': row[1],
                'short_description': row[2],
                'description': row[3],
                'status': row[4],
                'priority': row[5],
                'deadline': row[6],
                'created_at': row[7],
                'author_name': row[8],
                'executor_name': row[9],
                'creator_name': row[10],
                'author_id': row[11]
            })
        return tasks
    except Exception as e:
        print(f"Ошибка получения задач: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def get_task_detail(task_id):
    """Получить детальную информацию о задаче."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        _ensure_tasks_short_description_column(cursor)
        
        # Основная информация - получаем как старые поля, так и новые из связанных таблиц
        cursor.execute("""
            SELECT 
                t.id,
                t.title,
                t.short_description,
                t.description,
                t.status,
                t.priority,
                t.deadline,
                t.created_at,
                a.last_name || ' ' || a.first_name as author_name,
                e.last_name || ' ' || e.first_name as executor_name,
                c.last_name || ' ' || c.first_name as creator_name,
                ts.code as status_code,
                ts.title as status_title,
                ts.color as status_color,
                tp.code as priority_code,
                tp.title as priority_title,
                tp.color as priority_color,
                t.author_id
            FROM tasks t
            JOIN employees a ON t.author_id = a.id
            JOIN employees e ON t.executor_id = e.id
            JOIN employees c ON t.created_by = c.id
            LEFT JOIN task_statuses ts ON t.status_id = ts.id
            LEFT JOIN task_priorities tp ON t.priority_id = tp.id
            WHERE t.id = %s
        """, (task_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        # Используем данные из связанных таблиц статусов/приоритетов если они есть, иначе старые поля
        task = {
            'id': row[0],
            'title': row[1],
            'short_description': row[2],
            'description': row[3],
            'status': row[12] if row[12] else row[4],  # status_title или status
            'status_code': row[11] if row[11] else None,  # status_code
            'status_color': row[13] if row[13] else None,  # status_color
            'priority': row[15] if row[15] else row[5],  # priority_title или priority
            'priority_code': row[14] if row[14] else None,  # priority_code
            'priority_color': row[16] if row[16] else None,  # priority_color
            'deadline': row[6],
            'created_at': row[7],
            'author_name': row[8],
            'executor_name': row[9],
            'creator_name': row[10],
            'author_id': row[17],
            'observers': [],
            'tags': []
        }
        
        # Наблюдатели
        cursor.execute("""
            SELECT emp.last_name || ' ' || emp.first_name
            FROM task_observers tobs
            JOIN employees emp ON tobs.employee_id = emp.id
            WHERE tobs.task_id = %s
        """, (task_id,))
        task['observers'] = [r[0] for r in cursor.fetchall()]
        
        # Теги
        cursor.execute("""
            SELECT tt.name, tt.color
            FROM task_tags_link ttl
            JOIN task_tags tt ON ttl.tag_id = tt.id
            WHERE ttl.task_id = %s
        """, (task_id,))
        task['tags'] = [{'name': r[0], 'color': r[1]} for r in cursor.fetchall()]
        
        # Комментарии
        cursor.execute("""
            SELECT 
                tc.id,
                tc.comment_text,
                tc.created_at,
                tc.author_id,
                e.last_name || ' ' || e.first_name as author_name
            FROM task_comments tc
            JOIN employees e ON tc.author_id = e.id
            WHERE tc.task_id = %s
            ORDER BY tc.created_at ASC
        """, (task_id,))
        task['comments'] = []
        for row in cursor.fetchall():
            task['comments'].append({
                'id': row[0],
                'text': row[1],
                'created_at': row[2].strftime("%d.%m.%Y %H:%M") if row[2] else "",
                'author_id': row[3],
                'author_name': row[4]
            })
        
        return task
    except Exception as e:
        print(f"Ошибка получения детали задачи: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


def get_task_comments(task_id):
    """Получить список комментариев к задаче."""
    conn = get_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                tc.id,
                tc.comment_text,
                tc.created_at,
                tc.author_id,
                e.last_name || ' ' || e.first_name as author_name

            FROM task_comments tc
            JOIN employees e ON tc.author_id = e.id
            WHERE tc.task_id = %s
            ORDER BY tc.created_at ASC
        """, (task_id,))
        
        comments = []
        for row in cursor.fetchall():
            comments.append({
                'id': row[0],
                'text': row[1],
                'created_at': row[2].strftime("%d.%m.%Y %H:%M") if row[2] else "",
                'author_id': row[3],
                'author_name': row[4]
            })
        return comments
    except Exception as e:
        print(f"Ошибка получения комментариев: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def add_task_comment(task_id, author_id, comment_text, images=None):
    """Добавить комментарий к задаче."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO task_comments (task_id, author_id, comment_text)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (task_id, author_id, comment_text))
        comment_id = cursor.fetchone()[0]
        _save_image_attachments(cursor, 'comment', comment_id, images)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Ошибка добавления комментария: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def update_task_comment(comment_id, user_id, new_text):
    """Обновить текст комментария (только если пользователь - автор)."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE task_comments
            SET comment_text = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND author_id = %s
        """, (new_text, comment_id, user_id))
        conn.commit()
        success = cursor.rowcount > 0
        return success
    except Exception as e:
        conn.rollback()
        print(f"Ошибка обновления комментария: {e}")
        return False
    finally:
        cursor.close()
        conn.close()


def delete_task_comment(comment_id, user_id):
    """Удалить комментарий (только если пользователь - автор)."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM task_comments
            WHERE id = %s AND author_id = %s
        """, (comment_id, user_id))
        deleted = cursor.rowcount > 0
        if deleted:
            cursor.execute("DELETE FROM image_attachments WHERE owner_type = 'comment' AND owner_id = %s", (comment_id,))
        conn.commit()
        return deleted
    except Exception as e:
        conn.rollback()
        print(f"Ошибка удаления комментария: {e}")
        return False
    finally:
        cursor.close()
        conn.close()
