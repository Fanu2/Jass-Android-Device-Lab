import csv
import re
import time
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QStatusBar,
    QTextEdit, QVBoxLayout, QWidget, QInputDialog, QComboBox, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QDialog, QDialogButtonBox, QTreeWidget, QTreeWidgetItem, QProgressDialog, QCheckBox, QHeaderView, QSplitter
)

APP_NAME = "JASS Android Device Lab"
VERSION = "1.6.0"


class ADB:
    def __init__(self, preferred=None):
        self.exe = self.find_adb(preferred)

    @staticmethod
    def find_adb(preferred=None):
        candidates = []

        if preferred:
            candidates.append(Path(preferred))

        found = shutil.which("adb")
        if found:
            candidates.append(Path(found))

        for env_name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
            root = os.environ.get(env_name)
            if root:
                candidates.append(Path(root) / "platform-tools" / "adb.exe")

        home = Path.home()
        candidates += [
            home / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools" / "adb.exe",
            Path(r"C:\Android\platform-tools\adb.exe"),
            home / "Downloads" / "platform-tools" / "adb.exe",
            home / "Downloads" / "platform-tools-latest-windows" / "platform-tools" / "adb.exe",
        ]

        seen = set()
        for candidate in candidates:
            try:
                p = candidate.expanduser().resolve()
            except Exception:
                p = Path(candidate)

            key = str(p).lower()
            if key in seen:
                continue
            seen.add(key)

            if p.is_file() and p.name.lower() == "adb.exe":
                return str(p)

        return None

    def run(self, *args, timeout=12):
        if not self.exe:
            return False, "ADB not found. Use Browse ADB… to select adb.exe."

        try:
            result = subprocess.run(
                [self.exe, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return result.returncode == 0, (
                result.stdout or result.stderr
            ).strip()
        except Exception as exc:
            return False, str(exc)

    def shell(self, serial, command):
        return self.run("-s", serial, "shell", command)

    def devices(self):
        ok, output = self.run("devices")
        if not ok:
            return []

        devices = []
        for line in output.splitlines():
            line = line.strip()
            if not line or line.startswith("*") or line.startswith("List of devices"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                devices.append((parts[0], parts[1]))
        return devices


    def packages(self, serial):
        # -f includes APK path; -U includes UID where supported.
        ok, output = self.run("-s", serial, "shell", "pm", "list", "packages", "-f", "-U")
        return output if ok else ""

    def package_details(self, serial, package):
        ok, output = self.run(
            "-s", serial, "shell", "dumpsys", "package", package, timeout=20
        )
        return output if ok else ""

    def apk_path(self, serial, package):
        ok, output = self.run("-s", serial, "shell", "pm", "path", package)
        return output if ok else ""

    def pull(self, serial, remote, local):
        if not self.exe:
            return False, "ADB not found."
        try:
            result = subprocess.run(
                [self.exe, "-s", serial, "pull", remote, local],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return result.returncode == 0, (result.stdout or result.stderr).strip()
        except Exception as exc:
            return False, str(exc)


    def shell_output(self, serial, command, timeout=20):
        return self.shell(serial, command)

    def file_list(self, serial, remote):
        # Android 9 on the test device supports ls -la. We deliberately use
        # shell output instead of assuming a particular Android file API.
        ok, output = self.shell(serial, f'ls -la "{remote}"')
        return ok, output

    def pull_path(self, serial, remote, local):
        return self.pull(serial, remote, local)

    def remote_du(self, serial, path):
        ok, output = self.shell(serial, f'du -sk "{path}"')
        if not ok:
            return None
        first = output.strip().splitlines()
        if not first:
            return None
        try:
            return int(first[-1].split()[0]) * 1024
        except (ValueError, IndexError):
            return None

    def push_path(self, serial, local, remote):
        if not self.exe:
            return False, "ADB not found."
        try:
            result = subprocess.run(
                [self.exe, "-s", serial, "push", local, remote],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return result.returncode == 0, (result.stdout or result.stderr).strip()
        except Exception as exc:
            return False, str(exc)



class Card(QFrame):
    def __init__(self, title):
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        title_label = QLabel(title.upper())
        title_label.setStyleSheet("color:#8da2ba;font-size:11px")
        layout.addWidget(title_label)

        self.value = QLabel("—")
        self.value.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.value.setWordWrap(True)
        layout.addWidget(self.value)

    def set_value(self, value):
        self.value.setText(str(value))


class AppExplorer(QDialog):
    def __init__(self, adb, serial, parent=None):
        super().__init__(parent)
        self.adb = adb
        self.serial = serial
        self.rows = []
        self.setWindowTitle(f"JASS Android Device Lab — Installed Applications")
        self.resize(1050, 650)

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search app name or package name…")
        self.search.textChanged.connect(self.apply_filter)

        self.filter = QComboBox()
        self.filter.addItems(["All", "User Apps", "System Apps"])
        self.filter.currentTextChanged.connect(self.apply_filter)

        refresh = QPushButton("↻ Refresh")
        refresh.clicked.connect(self.load_packages)

        export_csv = QPushButton("Export CSV")
        export_csv.clicked.connect(self.export_csv)

        top.addWidget(QLabel("Search:"))
        top.addWidget(self.search, 1)
        top.addWidget(self.filter)
        top.addWidget(export_csv)
        top.addWidget(refresh)
        layout.addLayout(top)

        self.count_label = QLabel("0 packages")
        self.count_label.setStyleSheet("color:#8fa6bf")
        layout.addWidget(self.count_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Application / Package", "Type", "APK Path", "Version", "UID"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.itemSelectionChanged.connect(self.show_selected)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 310)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 300)
        self.table.setColumnWidth(3, 110)
        layout.addWidget(self.table, 1)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Select an application to inspect details.")
        self.details.setMaximumHeight(170)
        layout.addWidget(self.details)

        buttons = QHBoxLayout()
        self.export_button = QPushButton("Export APK")
        self.export_button.clicked.connect(self.export_apk)
        self.export_button.setEnabled(False)

        self.copy_path_button = QPushButton("Copy APK Path")
        self.copy_path_button.clicked.connect(self.copy_apk_path)
        self.copy_path_button.setEnabled(False)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)

        buttons.addWidget(self.export_button)
        buttons.addWidget(self.copy_path_button)
        buttons.addStretch()
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self.load_packages()

    def load_packages(self):
        self.count_label.setText("Reading package inventory…")
        QApplication.processEvents()

        raw = self.adb.packages(self.serial)
        self.rows = []

        for line in raw.splitlines():
            line = line.strip()
            if not line.startswith("package:"):
                continue

            body = line[len("package:"):]
            uid = ""
            if " uid:" in body:
                body, uid = body.rsplit(" uid:", 1)

            if "=" in body:
                apk_path, package = body.rsplit("=", 1)
            else:
                apk_path, package = "", body

            package = package.strip()
            apk_path = apk_path.strip()

            # Android's pm output does not reliably expose whether an app is
            # user/system in every version. Use the APK path as a transparent
            # heuristic rather than pretending it is definitive.
            app_type = (
                "System"
                if apk_path.startswith(("/system/", "/product/", "/vendor/", "/apex/"))
                else "User"
            )

            self.rows.append({
                "package": package,
                "apk": apk_path,
                "uid": uid,
                "type": app_type,
                "version": "",
            })

        # Fetch version names only for the discovered packages. Older Android
        # versions can return different dumpsys formatting, so parsing is
        # deliberately tolerant.
        for row in self.rows:
            details = self.adb.package_details(self.serial, row["package"])
            patterns = [
                r"versionName=([^\s]+)",
                r"versionName\s*=\s*([^\s]+)",
            ]
            for pattern in patterns:
                m = re.search(pattern, details)
                if m:
                    row["version"] = m.group(1)
                    break

        self.apply_filter()

    def apply_filter(self):
        needle = self.search.text().strip().lower()
        kind = self.filter.currentText()

        visible = []
        for row in self.rows:
            haystack = f'{row["package"]} {row["apk"]}'.lower()
            if needle and needle not in haystack:
                continue
            if kind == "User Apps" and row["type"] != "User":
                continue
            if kind == "System Apps" and row["type"] != "System":
                continue
            visible.append(row)

        self.table.setRowCount(0)

        for row in visible:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(row["package"]))
            self.table.setItem(r, 1, QTableWidgetItem(row["type"]))
            self.table.setItem(r, 2, QTableWidgetItem(row["apk"]))
            self.table.setItem(r, 3, QTableWidgetItem(row["version"] or "—"))
            self.table.setItem(r, 4, QTableWidgetItem(row["uid"] or "—"))

        total = len(self.rows)
        user_count = sum(1 for r in self.rows if r["type"] == "User")
        system_count = sum(1 for r in self.rows if r["type"] == "System")
        self.count_label.setText(
            f"{len(visible)} shown • {total} total • "
            f"{user_count} user • {system_count} system"
        )

        self.export_button.setEnabled(False)
        self.copy_path_button.setEnabled(False)
        self.details.clear()

    def selected_row(self):
        items = self.table.selectedItems()
        if not items:
            return None
        package = self.table.item(items[0].row(), 0).text()
        return next((r for r in self.rows if r["package"] == package), None)

    def show_selected(self):
        row = self.selected_row()
        if not row:
            self.export_button.setEnabled(False)
            self.copy_path_button.setEnabled(False)
            return

        details = self.adb.package_details(self.serial, row["package"])
        version_code = "—"
        m = re.search(r"versionCode=(\d+)", details)
        if m:
            version_code = m.group(1)

        text = (
            f'Package: {row["package"]}\n'
            f'Type: {row["type"]}\n'
            f'APK: {row["apk"]}\n'
            f'Version: {row["version"] or "—"}\n'
            f'Version code: {version_code}\n'
            f'UID: {row["uid"] or "—"}\n\n'
            f'ADB package details:\n{details[:12000]}'
        )
        self.details.setPlainText(text)
        self.export_button.setEnabled(bool(row["apk"]))
        self.copy_path_button.setEnabled(bool(row["apk"]))

    def export_csv(self):
        if not self.rows:
            QMessageBox.information(
                self, "Export CSV", "No packages are available to export."
            )
            return

        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export package inventory",
            str(Path.home() / "Downloads" / f"{self.serial}_packages.csv"),
            "CSV files (*.csv)"
        )
        if not destination:
            return

        try:
            with open(destination, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=["package", "type", "apk", "version", "uid"]
                )
                writer.writeheader()
                writer.writerows(self.rows)

            QMessageBox.information(
                self,
                "CSV Export",
                f"Package inventory exported successfully:\n\n{destination}"
            )
        except Exception as exc:
            QMessageBox.warning(self, "CSV Export", str(exc))

    def copy_apk_path(self):
        row = self.selected_row()
        if row:
            QApplication.clipboard().setText(row["apk"])

    def export_apk(self):
        row = self.selected_row()
        if not row:
            return

        remote = row["apk"]
        if not remote:
            QMessageBox.warning(self, "Export APK", "No APK path was reported.")
            return

        destination = QFileDialog.getExistingDirectory(
            self, "Choose APK archive folder", str(Path.home() / "Downloads")
        )
        if not destination:
            return

        safe_package = re.sub(r"[^A-Za-z0-9_.-]+", "_", row["package"])
        target = Path(destination) / f"{safe_package}.apk"

        # If pm reports an APK path, pull that exact file. If the app has
        # split APKs, pm path may return multiple paths; v1.1 exports the
        # primary path selected in the table and leaves split handling for
        # a later archive milestone.
        ok, output = self.adb.pull(self.serial, remote, str(target))

        if ok:
            QMessageBox.information(
                self, "APK Exported",
                f"APK exported successfully:\n\n{target}"
            )
        else:
            QMessageBox.warning(
                self, "APK Export",
                f"ADB could not export the APK.\n\n{output}"
            )


class FileLab(QDialog):
    def __init__(self, adb, serial, parent=None):
        super().__init__(parent)
        self.adb = adb
        self.serial = serial
        self.current_path = "/storage/emulated/0"
        self.setWindowTitle("JASS Android Device Lab — Device File Lab & Storage Analyzer")
        self.resize(1180, 760)

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.path_edit = QLineEdit(self.current_path)
        go = QPushButton("Go")
        go.clicked.connect(self.go_path)
        up = QPushButton("↑ Up")
        up.clicked.connect(self.go_up)
        refresh = QPushButton("↻ Refresh")
        refresh.clicked.connect(self.refresh_files)

        top.addWidget(QLabel("Remote path:"))
        top.addWidget(self.path_edit, 1)
        top.addWidget(go)
        top.addWidget(up)
        top.addWidget(refresh)
        layout.addLayout(top)

        shortcuts = QHBoxLayout()
        for label, path in [
            ("Internal Storage", "/storage/emulated/0"),
            ("Pictures", "/storage/emulated/0/Pictures"),
            ("DCIM", "/storage/emulated/0/DCIM"),
            ("Download", "/storage/emulated/0/Download"),
        ]:
            button = QPushButton(label)
            button.clicked.connect(
                lambda checked=False, p=path: self.goto_shortcut(p)
            )
            shortcuts.addWidget(button)
        layout.addLayout(shortcuts)

        tools = QHBoxLayout()
        self.show_hidden = QCheckBox("Show hidden")
        self.show_hidden.setChecked(False)
        self.show_hidden.stateChanged.connect(self.refresh_files)

        analyze = QPushButton("Analyze Folder")
        analyze.clicked.connect(self.analyze_folder)

        pull_folder = QPushButton("Pull Folder")
        pull_folder.clicked.connect(self.pull_folder)

        archive = QPushButton("Archive Folder")
        archive.clicked.connect(self.archive_folder)

        tools.addWidget(self.show_hidden)
        tools.addWidget(analyze)
        tools.addWidget(pull_folder)
        tools.addWidget(archive)
        tools.addStretch()
        layout.addLayout(tools)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(
            ["Name", "Type", "Size", "Permissions", "Modified"]
        )
        self.tree.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tree.itemDoubleClicked.connect(self.open_item)
        self.tree.setSortingEnabled(True)
        self.tree.setColumnWidth(0, 390)
        self.tree.setColumnWidth(1, 120)
        self.tree.setColumnWidth(2, 120)
        self.tree.setColumnWidth(3, 170)
        layout.addWidget(self.tree, 1)

        self.info = QLabel(
            "Double-click a directory to enter it. "
            "Storage is accessed through /storage/emulated/0."
        )
        self.info.setStyleSheet("color:#8fa6bf")
        layout.addWidget(self.info)

        buttons = QHBoxLayout()

        pull = QPushButton("Pull Selected")
        pull.clicked.connect(self.pull_selected)

        push = QPushButton("Push File")
        push.clicked.connect(self.push_file)

        shell = QPushButton("Open Shell")
        shell.clicked.connect(self.open_shell)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)

        buttons.addWidget(pull)
        buttons.addWidget(push)
        buttons.addWidget(shell)
        buttons.addStretch()
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self.refresh_files()

    @staticmethod
    def human_size(value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return str(value)

        units = ["B", "KB", "MB", "GB", "TB"]
        for unit in units:
            if value < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(value)} B"
                return f"{value:.1f} {unit}"
            value /= 1024
        return str(value)

    @staticmethod
    def type_label(name, is_dir):
        if is_dir:
            return "Folder"
        suffix = Path(name).suffix.lower()
        mapping = {
            ".apk": "APK",
            ".pdf": "PDF",
            ".jpg": "Image",
            ".jpeg": "Image",
            ".png": "Image",
            ".webp": "Image",
            ".gif": "Image",
            ".mp4": "Video",
            ".mkv": "Video",
            ".3gp": "Video",
            ".mov": "Video",
            ".mp3": "Audio",
            ".wav": "Audio",
            ".m4a": "Audio",
            ".zip": "Archive",
            ".7z": "Archive",
            ".rar": "Archive",
            ".txt": "Text",
            ".doc": "Document",
            ".docx": "Document",
            ".xls": "Spreadsheet",
            ".xlsx": "Spreadsheet",
        }
        return mapping.get(suffix, "File")

    def goto_shortcut(self, path):
        self.current_path = path
        self.path_edit.setText(path)
        self.refresh_files()

    def go_path(self):
        path = self.path_edit.text().strip() or "/storage/emulated/0"
        self.current_path = path.rstrip("/") or "/"
        self.refresh_files()

    def go_up(self):
        if self.current_path == "/":
            return
        parent = str(Path(self.current_path).parent).replace("\\", "/")
        self.current_path = parent if parent else "/"
        self.path_edit.setText(self.current_path)
        self.refresh_files()

    def parse_ls(self, output):
        rows = []
        for line in output.splitlines():
            line = line.rstrip()
            if not line or line.startswith("total "):
                continue

            parts = line.split(None, 7)
            if len(parts) < 8:
                continue

            permissions, links, owner, group, size, date, time, name = parts
            is_symlink = permissions.startswith("l")
            is_dir = permissions.startswith("d")
            target = ""

            if is_symlink and " -> " in name:
                name, target = name.split(" -> ", 1)
                if name in ("/sdcard", "sdcard") and target.startswith("/mnt/user/0"):
                    target = "/storage/emulated/0"

            if not self.show_hidden.isChecked() and name.startswith("."):
                continue

            try:
                byte_size = int(size)
            except ValueError:
                byte_size = 0

            rows.append({
                "name": name,
                "type": "Link → Directory" if is_symlink and (
                    target.startswith("/")
                ) else self.type_label(name, is_dir),
                "size": size,
                "bytes": byte_size,
                "permissions": permissions,
                "modified": f"{date} {time}",
                "is_dir": is_dir or is_symlink,
                "is_symlink": is_symlink,
                "target": target,
            })
        return rows

    def refresh_files(self, *args):
        self.path_edit.setText(self.current_path)
        ok, output = self.adb.file_list(self.serial, self.current_path)
        self.tree.clear()

        if not ok:
            self.info.setText(
                f"Could not read: {self.current_path}\n{output}"
            )
            return

        rows = self.parse_ls(output)
        rows.sort(key=lambda r: (not r["is_dir"], r["name"].lower()))

        for row in rows:
            display_size = "—" if row["is_dir"] else self.human_size(row["bytes"])
            item = QTreeWidgetItem([
                row["name"],
                row["type"],
                display_size,
                row["permissions"],
                row["modified"],
            ])
            item.setData(0, 256, row)
            self.tree.addTopLevelItem(item)

        self.info.setText(
            f"{len(rows)} entries • {self.current_path}"
        )

    def selected(self):
        item = self.tree.currentItem()
        if not item:
            return None
        return item.data(0, 256)

    def open_item(self, item, column):
        row = item.data(0, 256)
        if not row or not row["is_dir"]:
            return

        if row.get("is_symlink") and row.get("target"):
            new_path = row["target"]
        elif self.current_path == "/":
            new_path = "/" + row["name"]
        else:
            new_path = self.current_path.rstrip("/") + "/" + row["name"]

        self.current_path = new_path
        self.path_edit.setText(new_path)
        self.refresh_files()

    def analyze_folder(self):
        size = self.adb.remote_du(self.serial, self.current_path)
        if size is None:
            QMessageBox.warning(
                self, "Storage Analysis",
                "Android could not calculate the folder size."
            )
            return

        ok, output = self.adb.file_list(self.serial, self.current_path)
        rows = self.parse_ls(output) if ok else []

        folders = []
        for row in rows:
            if row["is_dir"] and not row["name"] in (".", ".."):
                child = (
                    self.current_path.rstrip("/") + "/" + row["name"]
                )
                child_size = self.adb.remote_du(self.serial, child)
                folders.append(
                    (row["name"], child_size if child_size is not None else 0)
                )

        folders.sort(key=lambda x: x[1], reverse=True)

        lines = [
            "JASS Android Storage Analysis",
            "=" * 58,
            f"Device: {self.serial}",
            f"Path: {self.current_path}",
            f"Recursive size: {self.human_size(size)}",
            f"Entries: {len(rows)}",
            "",
            "Largest immediate directories:",
            "-" * 58,
        ]

        for name, child_size in folders[:15]:
            lines.append(f"{self.human_size(child_size):>12}  {name}")

        QMessageBox.information(
            self, "Storage Analysis", "\n".join(lines)
        )

    def pull_selected(self):
        row = self.selected()
        if not row:
            QMessageBox.information(self, "Pull", "Select a file first.")
            return
        if row["is_dir"]:
            QMessageBox.information(
                self, "Pull",
                "Use Pull Folder for directories."
            )
            return

        remote = self.current_path.rstrip("/") + "/" + row["name"]
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Save Android file",
            str(Path.home() / "Downloads" / row["name"]),
            "All files (*.*)"
        )
        if not destination:
            return

        ok, output = self.adb.pull_path(
            self.serial, remote, destination
        )
        if ok:
            QMessageBox.information(
                self, "Pull Complete",
                f"File pulled successfully:\n\n{destination}"
            )
        else:
            QMessageBox.warning(self, "Pull Failed", output)

    def pull_folder(self):
        row = self.selected()

        if row and row["is_dir"]:
            remote = self.current_path.rstrip("/") + "/" + row["name"]
            default_name = row["name"]
        else:
            remote = self.current_path
            default_name = Path(self.current_path).name or "AndroidStorage"

        destination = QFileDialog.getExistingDirectory(
            self,
            "Choose local destination",
            str(Path.home() / "Downloads")
        )
        if not destination:
            return

        local = Path(destination) / default_name
        local.parent.mkdir(parents=True, exist_ok=True)

        ok, output = self.adb.pull_path(
            self.serial, remote, str(local)
        )

        if ok:
            QMessageBox.information(
                self, "Folder Pull Complete",
                f"Folder pulled successfully:\n\n{local}\n\n{output}"
            )
        else:
            QMessageBox.warning(self, "Folder Pull Failed", output)

    def archive_folder(self):
        row = self.selected()
        if row and row["is_dir"]:
            remote = self.current_path.rstrip("/") + "/" + row["name"]
            archive_name = row["name"]
        else:
            remote = self.current_path
            archive_name = Path(self.current_path).name or "AndroidStorage"

        destination = QFileDialog.getExistingDirectory(
            self,
            "Choose archive destination",
            str(Path.home() / "Downloads")
        )
        if not destination:
            return

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_root = Path(destination) / (
            f"JASS_Android_Archive_{self.serial}_{stamp}"
        )
        archive_root.mkdir(parents=True, exist_ok=True)

        payload = archive_root / archive_name
        ok, output = self.adb.pull_path(
            self.serial, remote, str(payload)
        )

        if not ok:
            QMessageBox.warning(
                self, "Archive Failed",
                f"ADB could not pull the selected storage:\n\n{output}"
            )
            return

        manifest = archive_root / "SHA256SUMS.txt"
        report = archive_root / "ARCHIVE_REPORT.txt"

        file_count = 0
        total_bytes = 0

        with manifest.open("w", encoding="utf-8") as mf:
            for path in payload.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    digest = hashlib.sha256()
                    size = 0
                    with path.open("rb") as f:
                        for block in iter(lambda: f.read(1024 * 1024), b""):
                            digest.update(block)
                            size += len(block)

                    relative = path.relative_to(archive_root)
                    mf.write(f"{digest.hexdigest()}  {relative}\n")
                    file_count += 1
                    total_bytes += size
                except OSError:
                    continue

        report.write_text(
            "\n".join([
                "JASS Android Device Archive",
                "=" * 58,
                f"Created: {datetime.now():%Y-%m-%d %H:%M:%S}",
                f"Device serial: {self.serial}",
                f"Remote path: {remote}",
                f"Archive: {archive_root}",
                f"Files: {file_count}",
                f"Bytes: {total_bytes}",
                f"Human size: {self.human_size(total_bytes)}",
                "",
                "Integrity:",
                "SHA-256 manifest generated for every successfully archived file.",
            ]),
            encoding="utf-8"
        )

        QMessageBox.information(
            self,
            "Archive Complete",
            f"Android archive created successfully:\n\n{archive_root}\n\n"
            f"{file_count} files\n{self.human_size(total_bytes)}\n\n"
            "SHA256SUMS.txt created."
        )

    def push_file(self):
        local, _ = QFileDialog.getOpenFileName(
            self, "Select local file", str(Path.home())
        )
        if not local:
            return

        remote = self.current_path.rstrip("/") + "/" + Path(local).name
        ok, output = self.adb.push_path(
            self.serial, local, remote
        )

        if ok:
            QMessageBox.information(
                self, "Push Complete",
                f"File pushed to:\n\n{remote}"
            )
            self.refresh_files()
        else:
            QMessageBox.warning(self, "Push Failed", output)

    def open_shell(self):
        command, accepted = QInputDialog.getText(
            self,
            "ADB Shell",
            "Command:",
            text=f'ls -la "{self.current_path}"'
        )
        if not accepted or not command:
            return

        ok, output = self.adb.shell(self.serial, command)
        QMessageBox.information(
            self,
            "ADB Shell",
            output if output else (
                "Command completed." if ok else "Command failed."
            )
        )


class DeviceArchive(QDialog):
    def __init__(self, adb, serial, parent=None):
        super().__init__(parent)
        self.adb = adb
        self.serial = serial
        self.setWindowTitle("JASS Android Device Lab — Device Archive & Diagnostics")
        self.resize(900, 650)

        layout = QVBoxLayout(self)

        title = QLabel("📦 Device Archive & Diagnostics")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        layout.addWidget(title)

        self.info = QTextEdit()
        self.info.setReadOnly(True)
        self.info.setPlainText(
            "Create a local preservation snapshot of the connected Android device.\n\n"
            "The archive includes device properties, battery information, storage "
            "information, package inventory, and a SHA-256 manifest for generated "
            "archive files. Protected Android data is not bypassed."
        )
        layout.addWidget(self.info, 1)

        row = QHBoxLayout()
        create = QPushButton("Create Device Archive")
        create.clicked.connect(self.create_archive)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)

        row.addWidget(create)
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)

    def prop(self, key):
        ok, output = self.adb.shell(self.serial, f"getprop {key}")
        return output.strip() if ok else ""

    def create_archive(self):
        destination = QFileDialog.getExistingDirectory(
            self,
            "Choose archive destination",
            str(Path.home() / "Downloads")
        )
        if not destination:
            return

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        root = Path(destination) / (
            f"JASS_Android_Device_Archive_{self.serial}_{stamp}"
        )
        root.mkdir(parents=True, exist_ok=True)

        reports = root / "reports"
        reports.mkdir(exist_ok=True)

        screenshots = root / "screenshots"
        screenshots.mkdir(exist_ok=True)

        # Device properties.
        ok, props_raw = self.adb.shell(self.serial, "getprop")
        (reports / "device_properties.txt").write_text(
            props_raw if ok else "Unable to collect getprop output.",
            encoding="utf-8"
        )

        properties = {}
        if ok:
            for line in props_raw.splitlines():
                m = re.match(r"\[(.+?)\]: \[(.*?)\]", line)
                if m:
                    properties[m.group(1)] = m.group(2)

        # Battery.
        ok, battery_raw = self.adb.shell(
            self.serial, "dumpsys battery"
        )
        (reports / "battery_report.txt").write_text(
            battery_raw if ok else "Unable to collect battery report.",
            encoding="utf-8"
        )

        # Storage.
        ok, storage_raw = self.adb.shell(
            self.serial, "df -h /data"
        )
        (reports / "storage_report.txt").write_text(
            storage_raw if ok else "Unable to collect storage report.",
            encoding="utf-8"
        )

        # Memory.
        ok, memory_raw = self.adb.shell(
            self.serial, "cat /proc/meminfo"
        )
        (reports / "memory_report.txt").write_text(
            memory_raw if ok else "Unable to collect memory report.",
            encoding="utf-8"
        )

        # Package inventory.
        packages_raw = self.adb.packages(self.serial)
        (reports / "packages_raw.txt").write_text(
            str(packages_raw) if packages_raw else "No package inventory returned.",
            encoding="utf-8"
        )

        package_rows = []
        for line in packages_raw.splitlines():
            line = line.strip()
            if not line.startswith("package:"):
                continue
            body = line[len("package:"):]
            uid = ""
            if " uid:" in body:
                body, uid = body.rsplit(" uid:", 1)
            if "=" in body:
                apk, package = body.rsplit("=", 1)
            else:
                apk, package = "", body

            package_rows.append({
                "package": package.strip(),
                "apk": apk.strip(),
                "uid": uid.strip(),
            })

        with (reports / "packages.csv").open(
            "w", newline="", encoding="utf-8-sig"
        ) as f:
            writer = csv.DictWriter(
                f, fieldnames=["package", "apk", "uid"]
            )
            writer.writeheader()
            writer.writerows(package_rows)

        # ADB version.
        ok, adb_version = self.adb.run("version")
        (reports / "adb_version.txt").write_text(
            adb_version if ok else "Unable to collect ADB version.",
            encoding="utf-8"
        )

        # Screenshot.
        screenshot_path = screenshots / "device_screen.png"
        try:
            result = subprocess.run(
                [
                    self.adb.exe, "-s", self.serial,
                    "exec-out", "screencap", "-p"
                ],
                capture_output=True,
                timeout=20
            )
            if result.returncode == 0 and result.stdout:
                screenshot_path.write_bytes(result.stdout)
            else:
                screenshot_path = None
        except Exception:
            screenshot_path = None

        # Human-readable device report.
        report_lines = [
            "JASS Android Device Archive",
            "=" * 62,
            f"Created: {datetime.now():%Y-%m-%d %H:%M:%S}",
            f"Serial: {self.serial}",
            f"ADB: {self.adb.exe}",
            "",
            "Device",
            "-" * 62,
            f"Manufacturer: {properties.get('ro.product.manufacturer', '—')}",
            f"Model: {properties.get('ro.product.model', '—')}",
            f"Device: {properties.get('ro.product.device', '—')}",
            f"Android: {properties.get('ro.build.version.release', '—')}",
            f"SDK: {properties.get('ro.build.version.sdk', '—')}",
            f"Build: {properties.get('ro.build.display.id', '—')}",
            "",
            "Archive contents",
            "-" * 62,
            "reports/device_properties.txt",
            "reports/battery_report.txt",
            "reports/storage_report.txt",
            "reports/memory_report.txt",
            "reports/packages_raw.txt",
            "reports/packages.csv",
            "reports/adb_version.txt",
        ]

        if screenshot_path:
            report_lines.append("screenshots/device_screen.png")

        (root / "device_report.txt").write_text(
            "\n".join(report_lines),
            encoding="utf-8"
        )

        # JSON index.
        index = {
            "format": "JASS Android Device Archive",
            "version": "1.0",
            "created": datetime.now().isoformat(timespec="seconds"),
            "serial": self.serial,
            "adb": self.adb.exe,
            "device": {
                "manufacturer": properties.get(
                    "ro.product.manufacturer", ""
                ),
                "model": properties.get("ro.product.model", ""),
                "device": properties.get("ro.product.device", ""),
                "android": properties.get(
                    "ro.build.version.release", ""
                ),
                "sdk": properties.get("ro.build.version.sdk", ""),
                "build": properties.get(
                    "ro.build.display.id", ""
                ),
            },
            "package_count": len(package_rows),
            "screenshot": bool(screenshot_path),
        }

        (root / "ARCHIVE_INDEX.json").write_text(
            json.dumps(index, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        # SHA-256 all files in the archive except the manifest itself.
        manifest = root / "SHA256SUMS.txt"
        entries = []

        for path in sorted(root.rglob("*")):
            if not path.is_file() or path == manifest:
                continue

            digest = hashlib.sha256()
            try:
                with path.open("rb") as f:
                    for block in iter(
                        lambda: f.read(1024 * 1024), b""
                    ):
                        digest.update(block)

                relative = path.relative_to(root)
                entries.append(
                    f"{digest.hexdigest()}  {relative.as_posix()}"
                )
            except OSError:
                continue

        manifest.write_text(
            "\n".join(entries) + ("\n" if entries else ""),
            encoding="utf-8"
        )

        QMessageBox.information(
            self,
            "Device Archive Complete",
            f"Archive created successfully:\n\n{root}\n\n"
            f"Packages: {len(package_rows)}\n"
            f"SHA-256 entries: {len(entries)}"
        )



class LiveDeviceLab(QDialog):
    """Live monitoring dashboard using normal ADB shell access."""

    def __init__(self, adb, serial, parent=None):
        super().__init__(parent)
        self.adb = adb
        self.serial = serial
        self.setWindowTitle("JASS Android Device Lab — Live Device Lab")
        self.resize(980, 700)

        root = QVBoxLayout(self)
        title = QLabel(f"📊 Live Device Lab  •  {serial}")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        root.addWidget(title)

        self.status = QLabel("Refreshing…")
        self.status.setStyleSheet("color:#8fa6bf")
        root.addWidget(self.status)

        grid = QGridLayout()
        root.addLayout(grid)

        self.cpu = self._card(grid, "CPU", 0, 0)
        self.ram = self._card(grid, "RAM", 0, 1)
        self.battery = self._card(grid, "Battery", 1, 0)
        self.storage = self._card(grid, "Storage", 1, 1)
        self.network = self._card(grid, "Network", 2, 0)
        self.uptime = self._card(grid, "Uptime", 2, 1)

        group = QGroupBox("Top Processes")
        lay = QVBoxLayout(group)
        self.process_table = QTableWidget(0, 3)
        self.process_table.setHorizontalHeaderLabels(["PID", "CPU", "Process"])
        self.process_table.horizontalHeader().setStretchLastSection(True)
        self.process_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.process_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        lay.addWidget(self.process_table)
        root.addWidget(group, 1)

        buttons = QHBoxLayout()
        refresh = QPushButton("↻ Refresh Now")
        snapshot = QPushButton("📊 Save Snapshot")
        self.auto = QCheckBox("Auto refresh (3 sec)")
        self.auto.setChecked(True)
        close = QPushButton("Close")
        buttons.addWidget(refresh)
        buttons.addWidget(snapshot)
        buttons.addWidget(self.auto)
        buttons.addStretch()
        buttons.addWidget(close)
        root.addLayout(buttons)

        refresh.clicked.connect(self.refresh)
        snapshot.clicked.connect(self.save_snapshot)
        close.clicked.connect(self.accept)

        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self._auto_refresh)
        self.timer.start()

        self.refresh()

    def _card(self, grid, title, row, col):
        box = QGroupBox(title)
        value = QLabel("—")
        value.setWordWrap(True)
        value.setMinimumHeight(55)
        value.setStyleSheet("font-size:16px;font-weight:bold;")
        lay = QVBoxLayout(box)
        lay.addWidget(value)
        grid.addWidget(box, row, col)
        return value

    def _shell(self, command):
        """Return only ADB shell stdout/stderr text, not the (ok, output) tuple."""
        result = self.adb.shell(self.serial, command)
        if isinstance(result, tuple):
            ok, output = result
            return str(output or "")
        return str(result or "")

    def _auto_refresh(self):
        if self.auto.isChecked():
            self.refresh()

    def refresh(self):
        try:
            self._cpu()
            self._ram()
            self._battery()
            self._storage()
            self._network()
            self._uptime()
            self._processes()
            self.status.setText("Last refresh: " + datetime.now().strftime("%H:%M:%S"))
        except Exception as exc:
            self.status.setText(f"Refresh error: {exc}")

    def _cpu(self):
        def sample():
            text = self._shell("cat /proc/stat | head -1")
            if not text.startswith("cpu "):
                return None
            vals = [int(x) for x in text.split()[1:]]
            return sum(vals), (vals[3] if len(vals) > 3 else 0)

        a = sample()
        time.sleep(0.08)
        b = sample()
        if not a or not b:
            self.cpu.setText("Unavailable")
            return
        total_delta = b[0] - a[0]
        idle_delta = b[1] - a[1]
        pct = 0.0 if total_delta <= 0 else 100.0 * (total_delta - idle_delta) / total_delta
        cores = self._shell("grep -c '^processor' /proc/cpuinfo").strip()
        self.cpu.setText(f"{pct:.1f}%  •  {cores or '?'} logical CPU(s)")

    def _ram(self):
        text = self._shell("cat /proc/meminfo")
        values = {}
        for line in text.splitlines():
            m = re.match(r"(MemTotal|MemAvailable):\s+(\d+)", line)
            if m:
                values[m.group(1)] = int(m.group(2)) * 1024
        total = values.get("MemTotal")
        avail = values.get("MemAvailable")
        if total and avail is not None:
            used = total - avail
            self.ram.setText(
                f"{used/1024**3:.2f} / {total/1024**3:.2f} GB"
                f"  •  {used/total*100:.1f}% used"
            )
        else:
            self.ram.setText("Unavailable")

    def _battery(self):
        text = self._shell("dumpsys battery")
        def get(pattern):
            m = re.search(pattern, text)
            return m.group(1) if m else None
        parts = []
        level = get(r"level:\s*(\d+)")
        temp = get(r"temperature:\s*(\d+)")
        voltage = get(r"voltage:\s*(\d+)")
        status = get(r"status:\s*(\d+)")
        if level:
            parts.append(level + "%")
        if temp:
            parts.append(f"{int(temp)/10:.1f}°C")
        if voltage:
            volts_raw = int(voltage)
            # Some Android vendor builds expose voltage in microvolts,
            # while standard dumpsys battery commonly uses millivolts.
            volts = volts_raw / 1_000_000 if volts_raw >= 100_000 else volts_raw / 1000
            parts.append(f"{volts:.2f} V")
        states = {"2":"Charging", "3":"Discharging", "4":"Not charging", "5":"Full"}
        if status:
            parts.append(states.get(status, "Unknown"))
        self.battery.setText("  •  ".join(parts) if parts else "Unavailable")

    def _storage(self):
        fields = self._shell("df -h /data | tail -1").split()
        if len(fields) >= 5:
            self.storage.setText(
                f"{fields[2]} used / {fields[1]} total"
                f"  •  {fields[4]}  •  {fields[3]} free"
            )
        else:
            self.storage.setText("Unavailable")

    def _network(self):
        ip = self._shell(
            "ip -4 addr show 2>/dev/null | grep 'inet ' | "
            "grep -v '127.0.0.1' | head -3"
        ).strip()
        route = self._shell("ip route 2>/dev/null | head -2").strip()
        lines = []
        if ip:
            lines.append(ip)
        if route:
            lines.append(route)
        self.network.setText("\n".join(lines) if lines else "Unavailable")

    def _uptime(self):
        try:
            seconds = int(float(self._shell("cat /proc/uptime").split()[0]))
            days, rem = divmod(seconds, 86400)
            hours, rem = divmod(rem, 3600)
            minutes = rem // 60
            self.uptime.setText(f"{days}d {hours:02d}h {minutes:02d}m")
        except Exception:
            self.uptime.setText("Unavailable")

    def _processes(self):
        text = self._shell(
            "ps -A -o PID,USER,%CPU,NAME 2>/dev/null | head -21"
        )
        rows = []
        for line in text.splitlines()[1:]:
            parts = line.split(None, 3)
            if len(parts) == 4:
                rows.append([parts[0], parts[2], parts[3]])
            elif len(parts) == 3:
                rows.append(parts)
        self.process_table.setRowCount(0)
        for pid, cpu, name in rows:
            r = self.process_table.rowCount()
            self.process_table.insertRow(r)
            for c, value in enumerate((pid, cpu, name)):
                self.process_table.setItem(r, c, QTableWidgetItem(value))

    def save_snapshot(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Performance Snapshot",
            f"JASS_Performance_{self.serial}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text files (*.txt)"
        )
        if not path:
            return
        lines = [
            "JASS Android Device Lab — Performance Snapshot",
            "=" * 55,
            f"Serial: {self.serial}",
            f"Captured: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"CPU: {self.cpu.text()}",
            f"RAM: {self.ram.text()}",
            f"Battery: {self.battery.text()}",
            f"Storage: {self.storage.text()}",
            f"Uptime: {self.uptime.text()}",
            "",
            "Network:",
            self.network.text(),
            "",
            "Top Processes:",
        ]
        for r in range(self.process_table.rowCount()):
            lines.append(" | ".join(
                self.process_table.item(r, c).text()
                if self.process_table.item(r, c) else ""
                for c in range(3)
            ))
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        QMessageBox.information(self, "Snapshot Saved", f"Saved:\n{path}")




class DeviceDiagnostics(QDialog):
    """Run a structured, non-destructive diagnostic check against the device."""

    def __init__(self, adb, serial, parent=None):
        super().__init__(parent)
        self.adb = adb
        self.serial = serial
        self.setWindowTitle(f"JASS Android Device Lab — Device Diagnostics • {serial}")
        self.resize(980, 700)

        root = QVBoxLayout(self)

        title = QLabel("🩺 Device Diagnostics")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        root.addWidget(title)

        subtitle = QLabel(
            "Non-destructive ADB diagnostics. No root access or system changes are required."
        )
        subtitle.setStyleSheet("color:#8fa6bf")
        root.addWidget(subtitle)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Check", "Status", "Value", "Details"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)

        self.report = QTextEdit()
        self.report.setReadOnly(True)
        self.report.setMaximumHeight(190)
        root.addWidget(self.report)

        buttons = QHBoxLayout()
        run = QPushButton("▶ Run Diagnostics")
        save = QPushButton("💾 Save Diagnostic Report")
        close = QPushButton("Close")
        buttons.addWidget(run)
        buttons.addWidget(save)
        buttons.addStretch()
        buttons.addWidget(close)
        root.addLayout(buttons)

        run.clicked.connect(self.run_diagnostics)
        save.clicked.connect(self.save_report)
        close.clicked.connect(self.accept)

        self.results = []
        self.run_diagnostics()

    def shell(self, command):
        try:
            result = self.adb.shell(self.serial, command)
            if isinstance(result, tuple):
                return result[1] if len(result) > 1 else ""
            return result or ""
        except Exception as exc:
            return f"ERROR: {exc}"

    def add_result(self, name, status, value, details):
        self.results.append((name, status, value, details))
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, text in enumerate((name, status, value, details)):
            self.table.setItem(row, col, QTableWidgetItem(str(text)))

    def run_diagnostics(self):
        self.table.setRowCount(0)
        self.results = []

        # ADB connection / identity
        props = {}
        raw_props = self.shell(
            "getprop ro.product.manufacturer; "
            "getprop ro.product.model; "
            "getprop ro.build.version.release; "
            "getprop ro.build.version.sdk; "
            "getprop ro.build.display.id; "
            "getprop ro.product.cpu.abi"
        )
        vals = [x.strip() for x in raw_props.splitlines() if x.strip()]
        keys = ["manufacturer", "model", "android", "sdk", "build", "abi"]
        props = dict(zip(keys, vals))

        self.add_result(
            "ADB connection", "PASS",
            self.serial,
            "Device is reachable through the selected ADB connection."
        )

        self.add_result(
            "Device identity", "PASS",
            f"{props.get('manufacturer','')} {props.get('model','')}".strip(),
            f"Android {props.get('android','?')} • SDK {props.get('sdk','?')}"
        )

        self.add_result(
            "Build",
            "PASS" if props.get("build") else "WARN",
            props.get("build", "Unavailable"),
            f"ABI: {props.get('abi', 'Unavailable')}"
        )

        # Battery
        battery = self.shell("dumpsys battery")
        level = re.search(r"level:\s*(\d+)", battery)
        temp = re.search(r"temperature:\s*(\d+)", battery)
        voltage = re.search(r"voltage:\s*(\d+)", battery)
        status = re.search(r"status:\s*(\d+)", battery)
        battery_value = []
        if level:
            battery_value.append(f"{level.group(1)}%")
        if temp:
            battery_value.append(f"{int(temp.group(1))/10:.1f}°C")
        if voltage:
            raw = int(voltage.group(1))
            volts = raw / 1_000_000 if raw >= 100_000 else raw / 1000
            battery_value.append(f"{volts:.2f} V")
        states = {"2": "Charging", "3": "Discharging", "4": "Not charging", "5": "Full"}
        if status:
            battery_value.append(states.get(status.group(1), "Unknown"))

        battery_ok = bool(level and temp)
        self.add_result(
            "Battery telemetry",
            "PASS" if battery_ok else "WARN",
            " • ".join(battery_value) if battery_value else "Unavailable",
            "Read from dumpsys battery."
        )

        # Storage
        df = self.shell("df -h /data | tail -1").strip()
        fields = df.split()
        if len(fields) >= 5:
            storage_value = f"{fields[2]} used / {fields[1]} total / {fields[3]} free"
            storage_status = "PASS"
            storage_detail = f"{fields[4]} used"
        else:
            storage_value = "Unavailable"
            storage_status = "WARN"
            storage_detail = "Could not parse df output."
        self.add_result("Data storage", storage_status, storage_value, storage_detail)

        # Memory
        mem = self.shell("cat /proc/meminfo")
        total = avail = None
        for line in mem.splitlines():
            if line.startswith("MemTotal:"):
                m = re.search(r"(\d+)", line)
                total = int(m.group(1)) * 1024 if m else None
            elif line.startswith("MemAvailable:"):
                m = re.search(r"(\d+)", line)
                avail = int(m.group(1)) * 1024 if m else None

        if total and avail is not None:
            used = total - avail
            memory_value = f"{used/1024**3:.2f} / {total/1024**3:.2f} GB"
            memory_detail = f"{used/total*100:.1f}% used"
            memory_status = "PASS"
        else:
            memory_value = "Unavailable"
            memory_detail = "Could not read /proc/meminfo."
            memory_status = "WARN"
        self.add_result("Memory", memory_status, memory_value, memory_detail)

        # CPU / ABI
        cpu_count = self.shell("grep -c '^processor' /proc/cpuinfo").strip()
        self.add_result(
            "CPU",
            "PASS" if cpu_count.isdigit() else "WARN",
            f"{cpu_count} logical CPU(s)" if cpu_count.isdigit() else "Unavailable",
            f"ABI: {props.get('abi', 'Unavailable')}"
        )

        # Network
        net = self.shell(
            "ip -4 addr show | grep 'inet ' | grep -v '127.0.0.1' | head -5"
        ).strip()
        net_lines = []
        for line in net.splitlines():
            line = line.strip()
            if line.startswith("inet "):
                f = line.split()
                if len(f) >= 2:
                    net_lines.append(f"{f[1]} ({f[-1]})")
        self.add_result(
            "Network interface",
            "PASS" if net_lines else "WARN",
            ", ".join(net_lines) if net_lines else "No IPv4 address found",
            "Read from Android network interfaces."
        )

        # Uptime
        uptime = self.shell("cat /proc/uptime").strip()
        try:
            seconds = int(float(uptime.split()[0]))
            d, rem = divmod(seconds, 86400)
            h, rem = divmod(rem, 3600)
            m, _ = divmod(rem, 60)
            uptime_value = f"{d}d {h:02d}h {m:02d}m"
            uptime_status = "PASS"
        except Exception:
            uptime_value = "Unavailable"
            uptime_status = "WARN"
        self.add_result("System uptime", uptime_status, uptime_value, "/proc/uptime")

        # SELinux / root capability
        selinux = self.shell("getenforce 2>/dev/null").strip()
        root_id = self.shell("id").strip()
        root_possible = "uid=0" in root_id
        self.add_result(
            "SELinux",
            "PASS" if selinux else "WARN",
            selinux or "Unavailable",
            "Normal Android security state inspection."
        )
        self.add_result(
            "ADB privilege",
            "INFO",
            "root" if root_possible else "shell",
            "This tool does not attempt privilege escalation."
        )

        # USB debugging / screen state
        usb = self.shell("getprop sys.usb.state").strip()
        screen = self.shell("dumpsys power | grep -m1 'Display Power'").strip()
        self.add_result(
            "USB state",
            "PASS" if usb else "WARN",
            usb or "Unavailable",
            "Current Android USB state."
        )
        self.add_result(
            "Display power",
            "INFO",
            screen or "Unavailable",
            "Current display power service state."
        )

        # Package inventory
        packages = self.adb.packages(self.serial)
        package_text = packages if isinstance(packages, str) else str(packages or "")
        package_count = sum(
            1 for line in package_text.splitlines()
            if line.strip().startswith("package:")
        )
        self.add_result(
            "Package inventory",
            "PASS" if package_text else "WARN",
            f"{package_count} package line(s)",
            "Collected using standard ADB package listing."
        )

        # Final summary
        passes = sum(1 for x in self.results if x[1] == "PASS")
        warns = sum(1 for x in self.results if x[1] == "WARN")
        infos = sum(1 for x in self.results if x[1] == "INFO")

        lines = [
            "JASS Android Device Lab — Diagnostic Report",
            "=" * 60,
            f"Captured: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Serial: {self.serial}",
            "",
            f"PASS: {passes}   WARN: {warns}   INFO: {infos}",
            "",
        ]
        for name, status, value, details in self.results:
            lines.append(f"[{status}] {name}: {value}")
            lines.append(f"       {details}")
        self.report.setPlainText("\n".join(lines))

    def save_report(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Diagnostic Report",
            f"JASS_Device_Diagnostics_{self.serial}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text files (*.txt)"
        )
        if not path:
            return
        Path(path).write_text(self.report.toPlainText(), encoding="utf-8")
        QMessageBox.information(self, "Saved", f"Diagnostic report saved to:\n{path}")


class ArchiveManager(QDialog):
    """Browse, verify and compare JASS Android Device archives."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("JASS Android Device Lab — Archive Manager")
        self.resize(1120, 700)
        self.archive_root = Path.home() / "Downloads"

        layout = QVBoxLayout(self)

        title = QLabel("📚 Android Archive Manager")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        layout.addWidget(title)

        subtitle = QLabel(
            "Browse preserved device snapshots, verify SHA-256 manifests, "
            "and compare archive metadata."
        )
        subtitle.setStyleSheet("color:#8fa6bf")
        layout.addWidget(subtitle)

        controls = QHBoxLayout()
        self.root_edit = QLineEdit(str(self.archive_root))
        browse = QPushButton("Browse Root…")
        scan = QPushButton("↻ Scan")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search serial, model, Android, build…")

        controls.addWidget(QLabel("Archive root:"))
        controls.addWidget(self.root_edit, 1)
        controls.addWidget(browse)
        controls.addWidget(scan)
        controls.addWidget(self.search, 1)
        layout.addLayout(controls)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Created", "Serial", "Manufacturer", "Model",
            "Android", "SDK", "Packages", "Archive"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(150)
        layout.addWidget(self.details)

        actions = QHBoxLayout()
        verify = QPushButton("🔐 Verify SHA-256")
        compare = QPushButton("📊 Compare Selected")
        report = QPushButton("📄 View Report")
        folder = QPushButton("📂 Open Folder")
        screenshot = QPushButton("📸 View Screenshot")
        close = QPushButton("Close")

        for b in (verify, compare, report, folder, screenshot):
            actions.addWidget(b)
        actions.addStretch()
        actions.addWidget(close)
        layout.addLayout(actions)

        browse.clicked.connect(self.choose_root)
        scan.clicked.connect(self.scan)
        self.search.textChanged.connect(self.filter_rows)
        self.table.itemSelectionChanged.connect(self.show_details)
        self.table.cellDoubleClicked.connect(lambda *_: self.view_report())
        verify.clicked.connect(self.verify_selected)
        compare.clicked.connect(self.compare_selected)
        report.clicked.connect(self.view_report)
        folder.clicked.connect(self.open_folder)
        screenshot.clicked.connect(self.view_screenshot)
        close.clicked.connect(self.accept)

        self.db_path = None
        self.records = []
        self.scan()

    def choose_root(self):
        path = QFileDialog.getExistingDirectory(
            self, "Choose Archive Root", str(self.archive_root)
        )
        if path:
            self.root_edit.setText(path)
            self.scan()

    def _db_connect(self):
        root = Path(self.root_edit.text().strip())
        root.mkdir(parents=True, exist_ok=True)
        self.db_path = root / "JASS_Android_Archive_Manager.sqlite3"
        con = sqlite3.connect(self.db_path)
        con.execute("""
            CREATE TABLE IF NOT EXISTS archives (
                archive_path TEXT PRIMARY KEY,
                created TEXT,
                serial TEXT,
                manufacturer TEXT,
                model TEXT,
                android TEXT,
                sdk TEXT,
                build TEXT,
                package_count INTEGER,
                screenshot INTEGER,
                updated TEXT
            )
        """)
        con.commit()
        return con

    def scan(self):
        root = Path(self.root_edit.text().strip())
        if not root.exists():
            self.details.setPlainText("Archive root does not exist.")
            return

        self.archive_root = root
        self.records = []

        for index_path in sorted(root.rglob("ARCHIVE_INDEX.json")):
            archive = index_path.parent
            try:
                data = json.loads(index_path.read_text(encoding="utf-8"))
                device = data.get("device", {})
                record = {
                    "path": archive,
                    "created": data.get("created", ""),
                    "serial": data.get("serial", ""),
                    "manufacturer": device.get("manufacturer", ""),
                    "model": device.get("model", ""),
                    "android": device.get("android", ""),
                    "sdk": device.get("sdk", ""),
                    "build": device.get("build", ""),
                    "package_count": data.get("package_count", 0),
                    "screenshot": data.get("screenshot", False),
                }
                self.records.append(record)
            except Exception:
                continue

        self._update_database()
        self.populate()

    def _update_database(self):
        try:
            con = self._db_connect()
            now = datetime.now().isoformat(timespec="seconds")
            for r in self.records:
                con.execute("""
                    INSERT INTO archives
                    (archive_path, created, serial, manufacturer, model,
                     android, sdk, build, package_count, screenshot, updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(archive_path) DO UPDATE SET
                      created=excluded.created,
                      serial=excluded.serial,
                      manufacturer=excluded.manufacturer,
                      model=excluded.model,
                      android=excluded.android,
                      sdk=excluded.sdk,
                      build=excluded.build,
                      package_count=excluded.package_count,
                      screenshot=excluded.screenshot,
                      updated=excluded.updated
                """, (
                    str(r["path"]), r["created"], r["serial"],
                    r["manufacturer"], r["model"], r["android"],
                    r["sdk"], r["build"], int(r["package_count"] or 0),
                    int(bool(r["screenshot"])), now
                ))
            con.commit()
            con.close()
        except Exception:
            pass

    def populate(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        query = self.search.text().strip().lower()

        for r in self.records:
            haystack = " ".join(
                str(r.get(k, "")) for k in
                ("created", "serial", "manufacturer", "model",
                 "android", "sdk", "build", "path")
            ).lower()
            if query and query not in haystack:
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                r["created"], r["serial"], r["manufacturer"], r["model"],
                r["android"], r["sdk"], str(r["package_count"]),
                r["path"].name
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, str(r["path"]))
                self.table.setItem(row, col, item)

        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        self.details.setPlainText(
            f"{self.table.rowCount()} archive(s) shown • "
            f"{len(self.records)} archive(s) indexed"
        )

    def filter_rows(self):
        self.populate()

    def selected_records(self):
        paths = []
        for item in self.table.selectedItems():
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and path not in paths:
                paths.append(path)

        result = []
        for p in paths:
            for r in self.records:
                if str(r["path"]) == p:
                    result.append(r)
                    break
        return result

    def show_details(self):
        selected = self.selected_records()
        if not selected:
            return
        r = selected[0]
        lines = [
            f"Archive: {r['path']}",
            f"Created: {r['created']}",
            f"Serial: {r['serial']}",
            f"Device: {r['manufacturer']} {r['model']}",
            f"Android: {r['android']}  •  SDK {r['sdk']}",
            f"Build: {r['build']}",
            f"Packages: {r['package_count']}",
            f"Screenshot: {'Yes' if r['screenshot'] else 'No'}",
        ]
        self.details.setPlainText("\n".join(lines))

    def verify_archive(self, archive):
        manifest = archive / "SHA256SUMS.txt"
        if not manifest.exists():
            return False, "SHA256SUMS.txt is missing."

        checked = 0
        failures = []
        try:
            for line in manifest.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split("  ", 1)
                if len(parts) != 2:
                    failures.append(f"Invalid manifest line: {line}")
                    continue
                expected, relative = parts
                target = archive / relative
                if not target.is_file():
                    failures.append(f"Missing: {relative}")
                    continue

                digest = hashlib.sha256()
                with target.open("rb") as f:
                    for block in iter(lambda: f.read(1024 * 1024), b""):
                        digest.update(block)

                checked += 1
                if digest.hexdigest().lower() != expected.lower():
                    failures.append(f"Mismatch: {relative}")
        except Exception as exc:
            return False, f"Verification error: {exc}"

        if failures:
            return False, (
                f"Checked {checked} file(s).\n\n" +
                "\n".join(failures[:20])
            )
        return True, f"SHA-256 verification passed.\n\nChecked {checked} file(s)."

    def verify_selected(self):
        selected = self.selected_records()
        if not selected:
            QMessageBox.information(self, "Verify", "Select an archive first.")
            return

        messages = []
        all_ok = True
        for r in selected:
            ok, message = self.verify_archive(r["path"])
            all_ok = all_ok and ok
            messages.append(
                f"{'PASS' if ok else 'FAIL'} — {r['path'].name}\n{message}"
            )

        QMessageBox.information(
            self,
            "SHA-256 Verification",
            "\n\n".join(messages)
        )

    def compare_selected(self):
        selected = self.selected_records()
        if len(selected) != 2:
            QMessageBox.information(
                self,
                "Compare Archives",
                "Select exactly two archives to compare."
            )
            return

        a, b = selected
        fields = [
            ("Serial", "serial"),
            ("Manufacturer", "manufacturer"),
            ("Model", "model"),
            ("Android", "android"),
            ("SDK", "sdk"),
            ("Build", "build"),
            ("Package count", "package_count"),
            ("Screenshot", "screenshot"),
        ]

        lines = [
            "JASS Android Archive Comparison",
            "=" * 68,
            "",
            f"A: {a['path'].name}",
            f"   {a['path']}",
            "",
            f"B: {b['path'].name}",
            f"   {b['path']}",
            "",
            "Differences / common metadata",
            "-" * 68,
        ]

        differences = 0
        for label, key in fields:
            av = a.get(key, "")
            bv = b.get(key, "")
            if av != bv:
                differences += 1
                lines.append(f"{label}:")
                lines.append(f"  A: {av}")
                lines.append(f"  B: {bv}")
            else:
                lines.append(f"{label}: {av}  [same]")

        lines += [
            "",
            f"Metadata fields different: {differences}",
            "",
            "Note: this comparison uses ARCHIVE_INDEX.json metadata. "
            "It does not claim that every file or package is identical."
        ]

        dlg = QDialog(self)
        dlg.setWindowTitle("Archive Comparison")
        dlg.resize(900, 650)
        lay = QVBoxLayout(dlg)
        box = QTextEdit()
        box.setReadOnly(True)
        box.setPlainText("\n".join(lines))
        lay.addWidget(box)
        close = QPushButton("Close")
        close.clicked.connect(dlg.accept)
        lay.addWidget(close)
        dlg.exec()

    def view_report(self):
        selected = self.selected_records()
        if not selected:
            QMessageBox.information(self, "Report", "Select an archive first.")
            return

        report = selected[0]["path"] / "device_report.txt"
        if not report.exists():
            QMessageBox.warning(self, "Report", "device_report.txt not found.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Device Report — {selected[0]['path'].name}")
        dlg.resize(900, 650)
        lay = QVBoxLayout(dlg)
        box = QTextEdit()
        box.setReadOnly(True)
        box.setPlainText(report.read_text(encoding="utf-8", errors="replace"))
        lay.addWidget(box)
        close = QPushButton("Close")
        close.clicked.connect(dlg.accept)
        lay.addWidget(close)
        dlg.exec()

    def open_folder(self):
        selected = self.selected_records()
        if not selected:
            return
        path = selected[0]["path"]
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            QMessageBox.warning(self, "Open Folder", str(exc))

    def view_screenshot(self):
        selected = self.selected_records()
        if not selected:
            QMessageBox.information(
                self, "Screenshot", "Select an archive first."
            )
            return

        image = selected[0]["path"] / "screenshots" / "device_screen.png"
        if not image.exists():
            QMessageBox.information(
                self, "Screenshot", "This archive has no saved screenshot."
            )
            return

        try:
            if sys.platform.startswith("win"):
                os.startfile(str(image))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(image)])
            else:
                subprocess.Popen(["xdg-open", str(image)])
        except Exception as exc:
            QMessageBox.warning(self, "Screenshot", str(exc))


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.resize(1120, 750)

        self.adb = ADB()
        self.serial = ""

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background:#07101d;
                color:#e8eef6;
            }
            QGroupBox {
                border:1px solid #263b52;
                border-radius:9px;
                margin-top:12px;
                padding:12px;
            }
            QGroupBox::title {
                subcontrol-origin:margin;
                left:12px;
                padding:0 5px;
            }
            QLineEdit, QTextEdit {
                background:#0c1929;
                border:1px solid #2a4059;
                border-radius:6px;
                padding:7px;
                color:#e8eef6;
            }
            QPushButton {
                background:#14283e;
                border:1px solid #35516d;
                border-radius:6px;
                padding:8px 14px;
            }
            QPushButton:hover {
                background:#1b3957;
            }
            QFrame#card {
                background:#0c1929;
                border:1px solid #243a51;
                border-radius:9px;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        title = QLabel(f"📱 {APP_NAME}")
        title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        main_layout.addWidget(title)

        subtitle = QLabel(
            "ADB-powered Android device management • Device Archive & Diagnostics v1.7.1"
        )
        subtitle.setStyleSheet("color:#8fa6bf")
        main_layout.addWidget(subtitle)

        connection = QGroupBox("ADB Connection")
        row = QHBoxLayout(connection)

        self.adb_status = QLabel()
        row.addWidget(self.adb_status)

        self.serial_edit = QLineEdit()
        self.serial_edit.setPlaceholderText("Device serial")
        row.addWidget(self.serial_edit, 1)

        browse = QPushButton("Browse ADB…")
        browse.clicked.connect(self.browse_adb)
        row.addWidget(browse)

        refresh = QPushButton("↻ Refresh")
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)

        main_layout.addWidget(connection)

        self.name = QLabel("No Android device connected")
        self.name.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        main_layout.addWidget(self.name)

        grid = QGridLayout()
        self.cards = {}

        for index, key in enumerate([
            "Manufacturer", "Model", "Android", "SDK",
            "Build", "Device", "Battery", "Storage"
        ]):
            self.cards[key] = Card(key)
            grid.addWidget(self.cards[key], index // 4, index % 4)

        main_layout.addLayout(grid)

        tools = QGroupBox("Device Tools")
        tools_row = QHBoxLayout(tools)
        self.buttons = []

        for text, function in [
            ("📦 Apps", self.apps),
            ("📁 Files", self.files),
            ("📦 Archive", self.archive_device),
            ("📚 Archives", self.archive_manager),
            ("🩺 Diagnostics", self.diagnostics),
            ("📊 Live Lab", self.live_lab),
            ("📸 Screenshot", self.screenshot),
            ("↻ Reboot", self.reboot),
            ("⌘ ADB Shell", self.shell),
            ("▤ Logcat", self.logcat),
        ]:
            button = QPushButton(text)
            button.clicked.connect(function)
            button.setEnabled(False)
            self.buttons.append(button)
            tools_row.addWidget(button)

        main_layout.addWidget(tools)

        information = QGroupBox("Device Information")
        info_layout = QVBoxLayout(information)

        self.info = QTextEdit()
        self.info.setReadOnly(True)
        info_layout.addWidget(self.info)

        main_layout.addWidget(information, 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)

        QTimer.singleShot(300, self.refresh)

    def enable_tools(self, enabled):
        for button in self.buttons:
            button.setEnabled(enabled)

    def browse_adb(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select adb.exe",
            str(Path.home()),
            "ADB executable (adb.exe)"
        )
        if path:
            self.adb = ADB(path)
            self.refresh()

    def refresh(self):
        if not self.adb.exe:
            self.adb_status.setText("● ADB NOT FOUND")
            self.adb_status.setStyleSheet(
                "color:#ff9a9a;font-weight:bold"
            )
            self.name.setText(
                "ADB not detected — click Browse ADB… and select adb.exe"
            )
            self.enable_tools(False)
            self.status.showMessage("ADB executable not found.")
            return

        version_ok, version_output = self.adb.run("version")
        version_line = version_output.splitlines()[1] if (
            version_output and len(version_output.splitlines()) > 1
        ) else "ADB available"

        self.adb_status.setText("● ADB AVAILABLE")
        self.adb_status.setStyleSheet(
            "color:#9be7a8;font-weight:bold"
        )

        devices = self.adb.devices()

        if not devices:
            self.serial = ""
            self.serial_edit.clear()
            self.name.setText("No Android device connected")
            self.clear_cards()
            self.enable_tools(False)
            self.status.showMessage(f"{version_line} — connect an Android device.")
            return

        device = next(
            ((serial, state) for serial, state in devices if state == "device"),
            devices[0]
        )
        serial, state = device
        self.serial = serial
        self.serial_edit.setText(serial)

        if state != "device":
            self.name.setText(f"{serial} — ADB state: {state}")
            self.enable_tools(False)
            self.status.showMessage(f"Device state: {state}")
            return

        self.enable_tools(True)
        self.load_device(serial)
        self.status.showMessage(f"{version_line} • Connected: {serial}")

    def load_device(self, serial):
        ok, output = self.adb.shell(serial, "getprop")
        props = {}

        if ok:
            for line in output.splitlines():
                match = re.match(r"\[(.+?)\]: \[(.*?)\]", line)
                if match:
                    props[match.group(1)] = match.group(2)

        ok, output = self.adb.shell(serial, "dumpsys battery")
        battery = {}

        if ok:
            for line in output.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    battery[key.strip()] = value.strip()

        ok, output = self.adb.shell(serial, "df -h /data")
        storage = "Unavailable"

        if ok and len(output.splitlines()) > 1:
            fields = output.splitlines()[-1].split()
            if len(fields) >= 5:
                storage = (
                    f"{fields[2]} used / {fields[1]} total "
                    f"({fields[4]}) • {fields[3]} free"
                )

        values = {
            "Manufacturer": props.get("ro.product.manufacturer", "Unknown"),
            "Model": props.get("ro.product.model", "Unknown"),
            "Android": props.get("ro.build.version.release", "Unknown"),
            "SDK": props.get("ro.build.version.sdk", "Unknown"),
            "Build": props.get("ro.build.display.id", "Unknown"),
            "Device": props.get("ro.product.device", "Unknown"),
            "Battery": f'{battery.get("level", "—")}% • {battery.get("status", "—")}',
            "Storage": storage,
        }

        for key, value in values.items():
            self.cards[key].set_value(value)

        self.name.setText(
            f'{values["Manufacturer"]} {values["Model"]}  •  {serial}'
        )

        lines = [
            "JASS Android Device Lab — Device Snapshot",
            "=" * 60,
            f"Snapshot: {datetime.now():%Y-%m-%d %H:%M:%S}",
            f"ADB: {self.adb.exe}",
            f"Serial: {serial}",
            "",
        ]

        lines += [
            f"{key:15}: {value}"
            for key, value in values.items()
        ]

        lines += ["", "Battery details", "-" * 60]
        lines += [
            f"{key:20}: {value}"
            for key, value in battery.items()
        ]

        self.info.setPlainText("\n".join(lines))

    def clear_cards(self):
        for card in self.cards.values():
            card.set_value("—")
        self.info.clear()

    def apps(self):
        if not self.serial:
            return
        dialog = AppExplorer(self.adb, self.serial, self)
        dialog.exec()

    def diagnostics(self):
        if not self.serial:
            QMessageBox.warning(self, "No Device", "Connect an Android device first.")
            return
        DeviceDiagnostics(self.adb, self.serial, self).exec()

    def archive_manager(self):
        ArchiveManager(self).exec()

    def live_lab(self):
        if not self.serial:
            QMessageBox.warning(self, "No Device", "Connect an Android device first.")
            return
        LiveDeviceLab(self.adb, self.serial, self).exec()

    def archive_device(self):
        if not self.serial:
            return
        dialog = DeviceArchive(self.adb, self.serial, self)
        dialog.exec()

    def files(self):
        if not self.serial:
            return
        dialog = FileLab(self.adb, self.serial, self)
        dialog.exec()

    def screenshot(self):
        if not self.serial:
            return

        folder = (
            Path.home()
            / "Pictures"
            / "JASS_Android_Device_Lab"
        )
        folder.mkdir(parents=True, exist_ok=True)

        path = folder / (
            f"{self.serial}_{datetime.now():%Y%m%d_%H%M%S}.png"
        )

        try:
            result = subprocess.run(
                [
                    self.adb.exe, "-s", self.serial,
                    "exec-out", "screencap", "-p"
                ],
                capture_output=True,
                timeout=15
            )

            if result.returncode == 0 and result.stdout:
                path.write_bytes(result.stdout)
                QMessageBox.information(
                    self,
                    APP_NAME,
                    f"Screenshot saved:\n\n{path}"
                )
            else:
                QMessageBox.warning(
                    self,
                    APP_NAME,
                    (result.stderr or b"Screenshot failed").decode(
                        errors="replace"
                    )
                )
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))

    def reboot(self):
        if not self.serial:
            return

        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"Reboot {self.serial}?"
        )

        if answer == QMessageBox.StandardButton.Yes:
            self.adb.run("-s", self.serial, "reboot")

    def shell(self):
        if not self.serial:
            return

        command, accepted = QInputDialog.getText(
            self,
            "ADB Shell",
            "Command:",
            text="getprop ro.product.model"
        )

        if accepted and command:
            ok, output = self.adb.shell(self.serial, command)
            self.info.append(
                f"\n$ adb -s {self.serial} shell {command}\n"
                f"{output}"
            )

    def logcat(self):
        if not self.serial:
            return

        ok, output = self.adb.run(
            "-s", self.serial,
            "logcat", "-d", "-t", "120",
            timeout=20
        )

        if ok:
            self.info.setPlainText(output)
        else:
            QMessageBox.warning(self, APP_NAME, output)


def main():
    app = QApplication(sys.argv)
    window = Main()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
