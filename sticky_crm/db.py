"""
Работа с базой данных.
"""

import psycopg2
from datetime import datetime
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
        # Сначала удаляем связанные уведомления
        cursor.execute("""
            DELETE FROM notifications
            WHERE message_id = %s
        """, (message_id,))
        # Затем удаляем само сообщение
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
                "INSERT INTO messages (chat_id, sender_id, message_text, is_forwarded, forwarded_from, forwarded_at) VALUES (%s, %s, %s, TRUE, %s, %s)",
                (target_chat_id, sender_id, forwarded_text, original_sender, current_time)
            )
        
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


def create_task(title, description, author_id, executor_id, observers_ids, deadline, priority, tag_ids, creator_id):
    """Создать новую задачу."""
    conn = get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        # Создаем задачу
        cursor.execute("""
            INSERT INTO tasks (title, description, author_id, executor_id, deadline, priority, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (title, description, author_id, executor_id, deadline, priority, creator_id))
        task_id = cursor.fetchone()[0]
        
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


def update_task(task_id, title=None, description=None, executor_id=None, status=None, priority=None, deadline=None, observers_ids=None, tag_ids=None):
    """Обновить задачу. Параметры могут быть None для частичного обновления."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        
        # Формируем динамический SQL для частичного обновления
        updates = []
        params = []
        
        if title is not None:
            updates.append("title=%s")
            params.append(title)
        if description is not None:
            updates.append("description=%s")
            params.append(description)
        if executor_id is not None:
            updates.append("executor_id=%s")
            params.append(executor_id)
        if status is not None:
            updates.append("status=%s")
            params.append(status)
        if priority is not None:
            updates.append("priority=%s")
            params.append(priority)
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
        
        conn.commit()
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
        
        # Удаляем связанные записи
        cursor.execute("DELETE FROM task_observers WHERE task_id = %s", (task_id,))
        cursor.execute("DELETE FROM task_tags_link WHERE task_id = %s", (task_id,))
        
        # Удаляем саму задачу
        cursor.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
        
        conn.commit()
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
        query = """
            SELECT 
                t.id,
                t.title,
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
                'description': row[2],
                'status': row[3],
                'priority': row[4],
                'deadline': row[5],
                'created_at': row[6],
                'author_name': row[7],
                'executor_name': row[8],
                'creator_name': row[9],
                'author_id': row[10]
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
        
        # Основная информация
        cursor.execute("""
            SELECT 
                t.id,
                t.title,
                t.description,
                t.status,
                t.priority,
                t.deadline,
                t.created_at,
                a.last_name || ' ' || a.first_name as author_name,
                e.last_name || ' ' || e.first_name as executor_name,
                c.last_name || ' ' || c.first_name as creator_name
            FROM tasks t
            JOIN employees a ON t.author_id = a.id
            JOIN employees e ON t.executor_id = e.id
            JOIN employees c ON t.created_by = c.id
            WHERE t.id = %s
        """, (task_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        task = {
            'id': row[0],
            'title': row[1],
            'description': row[2],
            'status': row[3],
            'priority': row[4],
            'deadline': row[5],
            'created_at': row[6],
            'author_name': row[7],
            'executor_name': row[8],
            'creator_name': row[9],
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
                'author_name': row[3]
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
                'author_name': row[3]
            })
        return comments
    except Exception as e:
        print(f"Ошибка получения комментариев: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def add_task_comment(task_id, author_id, comment_text):
    """Добавить комментарий к задаче."""
    conn = get_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO task_comments (task_id, author_id, comment_text)
            VALUES (%s, %s, %s)
        """, (task_id, author_id, comment_text))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Ошибка добавления комментария: {e}")
        return False
    finally:
        cursor.close()
        conn.close()
