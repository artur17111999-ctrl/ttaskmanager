import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from auth_window import AuthWindow
from main_window import MainWindow
from db import check_connection
from theme_manager import ThemeManager


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Sticky CRM")
    app.setStyle("Fusion")

    # Загружаем тему (QSS из папки styles/default)
    theme_manager = ThemeManager(app)
    theme_manager.load_theme("default")

    # Проверка подключения к БД
    success, message = check_connection()
    if not success:
        QMessageBox.critical(None, "Ошибка подключения",
                             f"Не удалось подключиться к базе данных:\n{message}")
        sys.exit(1)
    print(f"✅ {message}")

    auth = AuthWindow()
    if auth.exec() == AuthWindow.Accepted:
        user = auth.user_data
        print(f"✅ Вход выполнен: {user['full_name']}")
        main_window = MainWindow(user)
        main_window.show()
        sys.exit(app.exec())
    else:
        print("Вход отменён")
        sys.exit(0)


if __name__ == "__main__":
    main()