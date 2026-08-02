"""
Менеджер тем. Загружает QSS файлы из папки стилей.
"""

import os
from pathlib import Path
from PySide6.QtWidgets import QApplication


class ThemeManager:
    def __init__(self, app: QApplication, themes_dir: str = "styles"):
        self.app = app
        self.themes_dir = Path(__file__).parent / themes_dir
        self.current_theme = "default"

    def load_theme(self, theme_name: str = "default"):
        """Загрузить все QSS файлы из указанной темы и применить к приложению."""
        theme_path = self.themes_dir / theme_name
        if not theme_path.exists():
            print(f"Тема '{theme_name}' не найдена, используется default")
            theme_path = self.themes_dir / "default"

        combined_qss = ""

        for qss_file in sorted(theme_path.glob("*.qss")):
            print("ЗАГРУЖАЮ СТИЛЬ:", qss_file)

            try:
                with open(qss_file, "r", encoding="utf-8") as f:
                    content = f.read()

                    if "bubbleFrame" in content:
                        print(">>> НАЙДЕН bubbleFrame в:", qss_file)

                    combined_qss += content + "\n"

            except Exception as e:
                print(f"Ошибка чтения {qss_file}: {e}")

        self.app.setStyleSheet(combined_qss)
        self.current_theme = theme_name
        print(f"Тема '{theme_name}' загружена ({len(list(theme_path.glob('*.qss')))} файлов)")

    def reload_theme(self):
        """Перезагрузить текущую тему (удобно при разработке)."""
        self.load_theme(self.current_theme)

    def available_themes(self):
        """Список доступных тем (подпапок в styles/)."""
        return [d.name for d in self.themes_dir.iterdir() if d.is_dir()]
