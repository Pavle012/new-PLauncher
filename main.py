import sys
import os
import signal
import json
import requests
from PySide6.QtCore import QProcess, Qt, QSize, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout,
    QLabel, QPushButton, QHBoxLayout,
    QFileDialog, QMessageBox, QListWidget, QListWidgetItem,
    QAbstractItemView, QProgressDialog, QComboBox, QDialog,
    QPlainTextEdit
)
from PySide6.QtGui import QIcon, QPixmap

INSTANCES_FILE = "instances.json"
RELEASES_URL = "https://api.github.com/repos/Pavle012/Skakavi-krompir/releases"

class GameDownloader(QThread):
    progress = Signal(int)
    finished = Signal(str, str)  # (name, file_path)
    error = Signal(str)

    def __init__(self, download_url, asset_name, version_tag):
        super().__init__()
        self.download_url = download_url
        self.asset_name = asset_name
        self.version_tag = version_tag

    def run(self):
        try:
            base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")
            os.makedirs(base_dir, exist_ok=True)
            file_path = os.path.join(base_dir, self.asset_name)
            
            with requests.get(self.download_url, stream=True) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0
                
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                self.progress.emit(int(downloaded * 100 / total_size))
            
            if sys.platform != "win32":
                os.chmod(file_path, 0o755)
                
            self.finished.emit(f"Skakavi Krompir {self.version_tag}", file_path)
            
        except Exception as e:
            self.error.emit(str(e))

class VersionPicker(QWidget):
    def __init__(self, releases, parent=None):
        super().__init__(parent)
        self.releases = releases
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("Select Version:"))
        self.version_combo = QComboBox()
        for release in self.releases:
            self.version_combo.addItem(release["tag_name"], release)
        self.version_combo.currentIndexChanged.connect(self.update_assets)
        layout.addWidget(self.version_combo)
        
        layout.addWidget(QLabel("Select File:"))
        self.asset_combo = QComboBox()
        layout.addWidget(self.asset_combo)
        
        self.update_assets()
        self.auto_select_asset()

    def update_assets(self):
        self.asset_combo.clear()
        release = self.version_combo.currentData()
        if release:
            for asset in release.get("assets", []):
                self.asset_combo.addItem(asset["name"], asset)

    def auto_select_asset(self):
        if sys.platform == "win32":
            target = "Skakavi-krompir-Windows.exe"
        else:
            target = "Skakavi-Krompir-Linux"
            
        for i in range(self.asset_combo.count()):
            if self.asset_combo.itemText(i) == target:
                self.asset_combo.setCurrentIndex(i)
                break

    def get_selected(self):
        return self.version_combo.currentText(), self.asset_combo.currentData()

class LogViewer(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Game Logs")
        self.resize(600, 400)
        layout = QVBoxLayout(self)
        
        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("font-family: monospace; background-color: #1e1e1e; color: #d4d4d4;")
        layout.addWidget(self.text_edit)
        
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.text_edit.clear)
        layout.addWidget(clear_btn)

    def append_log(self, text):
        self.text_edit.appendPlainText(text)

class InstanceManager:
    def __init__(self):
        self.instances = self.load_instances()

    def load_instances(self):
        if os.path.exists(INSTANCES_FILE):
            try:
                with open(INSTANCES_FILE, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading instances: {e}")
        return []

    def save_instances(self):
        try:
            with open(INSTANCES_FILE, "w") as f:
                json.dump(self.instances, f, indent=4)
        except Exception as e:
            print(f"Error saving instances: {e}")

    def add_instance(self, name, path):
        self.instances.append({"name": name, "path": path})
        self.save_instances()

    def remove_instance(self, index):
        if 0 <= index < len(self.instances):
            del self.instances[index]
            self.save_instances()

instance_manager = InstanceManager()
process = None
downloader = None
log_viewer = None

def handle_finished(exit_code, exit_status):
    if exit_status == QProcess.ExitStatus.CrashExit:
        status.setText("Crashed")
    else:
        if exit_code == 0:
            status.setText("Finished")
        else:
            status.setText(f"Finished (Exit Code: {exit_code})")

def handle_error(error):
    if error == QProcess.ProcessError.FailedToStart:
        status.setText("Error: Binary not found or failed to start")
    else:
        status.setText(f"Process Error: {error}")

def read_stdout():
    if process and log_viewer:
        data = process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        log_viewer.append_log(data)

def read_stderr():
    if process and log_viewer:
        data = process.readAllStandardError().data().decode("utf-8", errors="replace")
        log_viewer.append_log(data)

def launch_instance():
    global process
    current_item = instance_list.currentItem()
    if not current_item:
        status.setText("No instance selected")
        return

    instance_index = instance_list.row(current_item)
    instance = instance_manager.instances[instance_index]
    instance_path = instance["path"]
    
    working_dir = os.path.dirname(instance_path)
    
    print(f"Launching Skakavi Krompir for instance: {instance['name']} at {instance_path}")
    status.setText(f"Launching {instance['name']}...")
    
    if log_viewer:
        log_viewer.append_log(f"--- Launching {instance['name']} ---\n")

    if process is None:
        process = QProcess()
        process.started.connect(lambda: status.setText(f"Running: {instance['name']}"))
        process.finished.connect(handle_finished)
        process.errorOccurred.connect(handle_error)
        process.readyReadStandardOutput.connect(read_stdout)
        process.readyReadStandardError.connect(read_stderr)

    if process.state() == QProcess.ProcessState.NotRunning:
        process.setWorkingDirectory(working_dir)
        if not os.path.exists(working_dir):
            os.makedirs(working_dir, exist_ok=True)
            
        process.start("setsid", [instance_path])
    else:
        status.setText("Already running")

def kill_instance():
    global process
    if process is not None and process.state() == QProcess.ProcessState.Running:
        pid = process.processId()
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()
            
        process.waitForFinished(1000)
        process = None
        status.setText("Killed")
    else:
        status.setText("Not running")

def add_new_instance():
    file_path, _ = QFileDialog.getOpenFileName(window, "Select Instance Executable or Configuration")
    if file_path:
        name = os.path.basename(file_path)
        instance_manager.add_instance(name, file_path)
        refresh_instances()

def remove_selected_instance():
    current_item = instance_list.currentItem()
    if not current_item:
        QMessageBox.warning(window, "Remove Instance", "No instance selected.")
        return

    instance_index = instance_list.row(current_item)
    instance_name = current_item.text()
    
    reply = QMessageBox.question(window, "Confirm Removal", 
                                 f"Are you sure you want to remove '{instance_name}'?\nThis will not delete the files, only the launcher entry.",
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    
    if reply == QMessageBox.Yes:
        instance_manager.remove_instance(instance_index)
        refresh_instances()

def show_logs():
    global log_viewer
    if not log_viewer:
        log_viewer = LogViewer(window)
    log_viewer.show()
    log_viewer.raise_()

def download_instance_dialog():
    progress = QProgressDialog("Fetching releases from GitHub...", None, 0, 0, window)
    progress.setWindowModality(Qt.WindowModal)
    progress.show()
    QApplication.processEvents()
    
    try:
        response = requests.get(RELEASES_URL)
        response.raise_for_status()
        releases = response.json()
        progress.close()
    except Exception as e:
        progress.close()
        QMessageBox.critical(window, "Error", f"Failed to fetch releases: {e}")
        return

    dialog = QMessageBox(window)
    dialog.setWindowTitle("Download Instance")
    dialog.setText("Select the version and file you want to download.")
    
    picker = VersionPicker(releases)
    dialog.layout().addWidget(picker)
    dialog.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
    
    if dialog.exec() == QMessageBox.Ok:
        version, asset = picker.get_selected()
        if asset:
            start_download(asset["browser_download_url"], asset["name"], version)

def start_download(url, filename, version):
    global downloader
    downloader = GameDownloader(url, filename, version)
    
    progress_dialog = QProgressDialog(f"Downloading {filename}...", "Cancel", 0, 100, window)
    progress_dialog.setWindowModality(Qt.WindowModal)
    
    downloader.progress.connect(progress_dialog.setValue)
    downloader.finished.connect(lambda name, path: handle_download_finished(name, path, progress_dialog))
    downloader.error.connect(lambda err: handle_download_error(err, progress_dialog))
    
    downloader.start()
    progress_dialog.exec()

def handle_download_finished(name, path, dialog):
    dialog.close()
    instance_manager.add_instance(name, path)
    refresh_instances()
    QMessageBox.information(window, "Success", f"Downloaded and added instance: {name}")

def handle_download_error(err, dialog):
    dialog.close()
    QMessageBox.critical(window, "Download Error", f"Failed to download: {err}")

def refresh_instances():
    instance_list.clear()
    icon = QIcon.fromTheme("applications-games", QIcon("icon.png")) 
    
    for inst in instance_manager.instances:
        item = QListWidgetItem(icon, inst["name"])
        item.setTextAlignment(Qt.AlignCenter)
        instance_list.addItem(item)

app = QApplication(sys.argv)

window = QWidget()
window.setWindowTitle("Skakavi krompir launcher")
window.resize(700, 500)

layout = QVBoxLayout(window)

title = QLabel("Skakavi krompir launcher")
title.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 10px;")
layout.addWidget(title)

status = QLabel("Ready")
status.setStyleSheet("font-size: 14px; color: #666; margin-bottom: 10px;")
layout.addWidget(status)

instance_list = QListWidget()
instance_list.setViewMode(QListWidget.IconMode)
instance_list.setIconSize(QSize(64, 64))
instance_list.setMovement(QListWidget.Static)
instance_list.setResizeMode(QListWidget.Adjust)
instance_list.setSpacing(10)
instance_list.setWrapping(True)
instance_list.itemDoubleClicked.connect(lambda: launch_instance())
refresh_instances()
layout.addWidget(instance_list, 1)

button_layout = QHBoxLayout()
add_inst_btn = QPushButton("Add")
add_inst_btn.clicked.connect(add_new_instance)

# upcoming feature
# rename_inst_btn = QPushButton("Rename")
# rename_inst_btn.clicked.connect(rename_selected_instance)

remove_inst_btn = QPushButton("Remove")
remove_inst_btn.clicked.connect(remove_selected_instance)

download_btn = QPushButton("Download")
download_btn.clicked.connect(download_instance_dialog)

log_btn = QPushButton("Logs")
log_btn.clicked.connect(show_logs)

launch_btn = QPushButton("Launch")
launch_btn.clicked.connect(launch_instance)

kill_btn = QPushButton("Kill")
kill_btn.clicked.connect(kill_instance)

button_layout.addWidget(add_inst_btn)
# button_layout.addWidget(rename_inst_btn) # upcoming feature
button_layout.addWidget(remove_inst_btn)
button_layout.addWidget(download_btn)
button_layout.addStretch()
button_layout.addWidget(log_btn)
button_layout.addWidget(kill_btn)
button_layout.addWidget(launch_btn)
layout.addLayout(button_layout)

# Initialize log viewer
log_viewer = LogViewer(window)

window.show()
sys.exit(app.exec())
