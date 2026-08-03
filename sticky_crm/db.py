"""
Работа с базой данных.
"""

import psycopg2
from config import DB_CONFIG


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
                   m.message_text, m.created_at, m.is_read, m.is_deleted, m.edited_at
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
                'time': row[4].strftime("%H:%M") if row[4] else "",
                'is_read': row[5],
                'is_deleted': row[6],
                'edited_at': row[7].strftime("%H:%M") if row[7] else None
            })
        return list(reversed(messages)) if order_desc else messages
    except Exception as e:
        print(f"Ошибка получения сообщений: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def send_message(chat_id, sender_id, text):
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
        conn.commit()

        # Уведомление для личных чатов
        cursor.execute("SELECT is_group FROM chats WHERE id = %s", (chat_id,))
        is_group = cursor.fetchone()[0]
        if not is_group:
            cursor.execute("""
                           SELECT cm.employee_id
                           FROM chat_members cm
                           WHERE cm.chat_id = %s
                             AND cm.employee_id != %s
                           """, (chat_id, sender_id))
            receiver = cursor.fetchone()
            if receiver:
                receiver_id = receiver[0]
                cursor.execute("SELECT last_name, first_name FROM employees WHERE id = %s", (sender_id,))
                sender_info = cursor.fetchone()
                sender_name = f"{sender_info[0]} {sender_info[1]}"
                create_notification(receiver_id, chat_id, message_id,
                                    f"Новое сообщение от {sender_name}: {text[:50]}")
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

def edit_message(message_id, new_text):
    """Редактировать сообщение. Возвращает True/False."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE messages 
            SET message_text = %s, edited_at = NOW()
            WHERE id = %s
        """, (new_text, message_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Ошибка редактирования: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def delete_message(message_id):
    """Полное удаление сообщения."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM messages
            WHERE id = %s
        """, (message_id,))
        conn.commit()
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
                   m.message_text, m.created_at, m.is_read, m.is_deleted, m.edited_at
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
                'time': row[4].strftime("%H:%M") if row[4] else "",
                'is_read': row[5],
                'is_deleted': row[6],
                'edited_at': row[7].strftime("%H:%M") if row[7] else None
            })
        return messages
    except Exception as e:
        print(f"Ошибка получения новых сообщений: {e}")
        return []
    finally:
        cursor.close()
        conn.close()