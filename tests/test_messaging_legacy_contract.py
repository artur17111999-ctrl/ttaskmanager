import inspect
import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "sticky_crm"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import db
from contacts_widget import ContactsWidget


class _MessageCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []
        self.closed = False

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchall(self):
        return list(self.rows)

    def close(self):
        self.closed = True


class _MessageConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


class MessagingLegacyContractTests(unittest.TestCase):
    def test_database_function_signatures_remain_compatible_with_widget(self):
        expected = {
            "get_contacts_and_groups": "(user_id, search_query=None)",
            "get_personal_chats": "(user_id)",
            "get_chat_messages": "(chat_id, limit=50, offset=0, order_desc=False)",
            "get_new_messages": "(chat_id, last_id)",
            "search_chat_messages": "(chat_id, query, limit=500)",
            "send_message": "(chat_id, sender_id, text, images=None)",
            "mark_messages_as_read": "(chat_id, user_id)",
            "edit_message": "(message_id, new_text, sender_id=None)",
            "delete_message": "(message_id, sender_id=None)",
            "forward_messages": "(target_chat_id, sender_id, messages_to_forward)",
            "create_group_chat_auto": "(user_id, member_ids)",
            "delete_group_chat": "(chat_id, user_id)",
        }
        for name, signature in expected.items():
            with self.subTest(name=name):
                self.assertTrue(hasattr(db, name))
                self.assertEqual(str(inspect.signature(getattr(db, name))), signature)

    def test_contacts_widget_navigation_contract_remains_available(self):
        self.assertEqual(
            str(inspect.signature(ContactsWidget.__init__)),
            "(self, current_user_id, parent=None)",
        )
        self.assertEqual(
            str(inspect.signature(ContactsWidget.open_chat_by_id)),
            "(self, chat_id)",
        )
        self.assertEqual(
            str(inspect.signature(ContactsWidget.open_message_by_id)),
            "(self, chat_id, message_id)",
        )

    def test_legacy_message_dictionary_shape_is_characterized(self):
        created_at = datetime(2026, 8, 6, 12, 34)
        cursor = _MessageCursor(
            [
                (
                    101,
                    7,
                    "Иванов Иван",
                    "legacy message",
                    created_at,
                    False,
                    False,
                    None,
                    False,
                    None,
                    None,
                )
            ]
        )
        connection = _MessageConnection(cursor)

        with patch.object(db, "get_connection", return_value=connection):
            messages = db.get_chat_messages(55, limit=50)

        self.assertEqual(len(messages), 1)
        self.assertEqual(
            set(messages[0]),
            {
                "id",
                "sender_id",
                "sender_name",
                "text",
                "created_at",
                "time",
                "is_read",
                "is_deleted",
                "edited_at",
                "is_forwarded",
                "forwarded_from",
                "forwarded_at",
            },
        )
        self.assertEqual(messages[0]["id"], 101)
        self.assertEqual(messages[0]["time"], "12:34")
        self.assertEqual(cursor.executed[0][1], (55, 50, 0))
        self.assertTrue(cursor.closed)
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
