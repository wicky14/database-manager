#!/usr/bin/env python3
"""
Database Manager
A modern database management tool for PostgreSQL, MySQL, SQLite, and SQL Server.

Usage:
    main.py            → Install/Uninstall mode with GUI confirmation
    main.py --app      → Launch application
    main.py install    → Force install (no prompt)
    main.py uninstall  → Force uninstall (no prompt)
"""

import sys
import os

from PySide6.QtWidgets import QApplication, QMessageBox


def _show_install_dialog():
    msg = QMessageBox()
    msg.setWindowTitle("Database Manager")
    msg.setText("Database Manager is not installed.")
    msg.setInformativeText("Do you want to install it?")
    install_btn = msg.addButton("Install", QMessageBox.ButtonRole.AcceptRole)
    cancel_btn = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    msg.setDefaultButton(install_btn)
    msg.exec()
    return msg.clickedButton() == install_btn


def _show_uninstall_dialog():
    msg = QMessageBox()
    msg.setWindowTitle("Database Manager")
    msg.setText("Database Manager is already installed.")
    msg.setInformativeText("What do you want to do?")

    run_btn = msg.addButton("Run", QMessageBox.ButtonRole.AcceptRole)
    uninstall_btn = msg.addButton("Uninstall", QMessageBox.ButtonRole.DestructiveRole)
    cancel_btn = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    msg.setDefaultButton(run_btn)
    msg.exec()

    clicked = msg.clickedButton()
    if clicked == uninstall_btn:
        return "uninstall"
    elif clicked == run_btn:
        return "run"
    return "cancel"


def main():
    args = sys.argv[1:]

    if "--app" in args:
        from installer.manager import run_app
        run_app()
        return

    app = QApplication(sys.argv)
    app.setApplicationName("Database Manager")

    if "install" in args:
        binary = sys.argv[0]
        if not os.path.isabs(binary):
            binary = os.path.abspath(binary)
        from installer.manager import install_with_progress
        if install_with_progress(binary):
            from installer.manager import run_app
            run_app()
        return

    if "uninstall" in args:
        from installer.manager import uninstall_with_progress
        uninstall_with_progress()
        return

    from installer.manager import is_installed, run_app

    if not is_installed():
        if _show_install_dialog():
            binary = sys.argv[0]
            if not os.path.isabs(binary):
                binary = os.path.abspath(binary)
            from installer.manager import install_with_progress
            if install_with_progress(binary):
                run_app()
    else:
        choice = _show_uninstall_dialog()
        if choice == "uninstall":
            from installer.manager import uninstall_with_progress
            uninstall_with_progress()
        elif choice == "run":
            run_app()


if __name__ == "__main__":
    main()
