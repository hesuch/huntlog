"""Huntlog for Windows. Qt and the local service share the application's lifetime."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import threading
import traceback


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        if not args.data_dir:
            parser.error("--self-test requires an isolated --data-dir")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
    root = Path(__file__).resolve().parent
    data = (args.data_dir or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "HuntlogDesktop").resolve()
    data.mkdir(parents=True, exist_ok=True)
    log = (data / "desktop.log").open("a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log

    from PySide6.QtCore import QLockFile, QStandardPaths, QTimer, QUrl, QObject, Signal
    from PySide6.QtGui import QAction, QDesktopServices, QIcon, QFont, QFontDatabase
    from PySide6.QtWidgets import (QApplication, QFileDialog, QMainWindow, QMessageBox,
                                  QDialog, QVBoxLayout, QLabel, QPlainTextEdit, QDialogButtonBox)
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from app import Handler, LocalHTTPServer, Store
    from wiki_assets import WikiSprites

    qt = QApplication([sys.argv[0]])
    qt.setApplicationName("Huntlog")
    qt.setOrganizationName("HuntlogDesktop")
    if args.self_test:
        for font in ("segoeui.ttf", "segoeuib.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font))
    qt.setFont(QFont("Segoe UI", 10))
    qt.setWindowIcon(QIcon(str(root / "static" / "favicon.svg")))
    lock = QLockFile(str(data / "app.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        if not args.self_test:
            QMessageBox.information(None, "Huntlog", "O Huntlog já está aberto. Procure a janela na barra de tarefas.")
        return 0

    class DesktopHandler(Handler):
        store = Store(data / "hunts.sqlite3")
        sprites = WikiSprites(root / "static" / "sprites", data / "sprites")

    # Keep the origin stable so favorites survive restarts. Never connect to the
    # user's separate browser edition or to an unrelated service on a busy port.
    settings_file = data / "desktop-settings.json"
    try:
        port = int(json.loads(settings_file.read_text(encoding="utf-8"))["port"])
        if not 1024 <= port <= 65535:
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        port = 18765
    try:
        server = LocalHTTPServer(("127.0.0.1", port), DesktopHandler)
    except OSError:
        server = LocalHTTPServer(("127.0.0.1", 0), DesktopHandler)
    port = server.server_port
    settings_file.write_text(json.dumps({"port": port}), encoding="utf-8")
    origin = f"http://127.0.0.1:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="Huntlog service")
    thread.start()

    window = QMainWindow()
    window.setWindowTitle("Huntlog · Diário de hunts")
    window.resize(1360, 900)
    window.setMinimumSize(900, 620)
    view = QWebEngineView(window)
    window.setCentralWidget(view)
    profile = QWebEngineProfile("Huntlog", window)
    profile.setPersistentStoragePath(str(data / "interface"))
    profile.setCachePath(str(data / "cache"))
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
    profile.setHttpAcceptLanguage("pt-BR,pt;q=0.9,en;q=0.5")

    class Page(QWebEnginePage):
        def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
            if url.host() == "127.0.0.1" and url.port() == port:
                return True
            if is_main_frame and url.scheme() in ("http", "https"):
                if not args.self_test:
                    QDesktopServices.openUrl(url)
            return False

        def javaScriptConsoleMessage(self, level, message, line, source):
            print(f"Web: {level}: {message} ({source}:{line})")

    page = Page(profile, view)
    view.setPage(page)
    page.newWindowRequested.connect(lambda request: QDesktopServices.openUrl(request.requestedUrl())
                                    if request.requestedUrl().scheme() in ("http", "https") and not args.self_test else None)
    downloads = []
    test_result = {"ok": False}

    def finish_test(result):
        test_result.update(result)
        (data / "self-test.json").write_text(json.dumps(test_result, ensure_ascii=False, indent=2), encoding="utf-8")
        def capture_and_close():
            window.grab().save(str(data / "window.png"))
            window.close()
        QTimer.singleShot(500, capture_and_close)

    def save_download(download):
        if args.self_test:
            filename = str(data / "export-test.json")
        else:
            directory = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
            image_download = download.mimeType() == "image/png"
            filename, _ = QFileDialog.getSaveFileName(window, "Salvar imagem" if image_download else "Salvar backup do Huntlog",
                                                     str(Path(directory) / download.suggestedFileName()),
                                                     "Imagem PNG (*.png)" if image_download else "Backup JSON (*.json)")
        if not filename:
            download.cancel()
            return
        path = Path(filename)
        download.setDownloadDirectory(str(path.parent))
        download.setDownloadFileName(path.name)
        downloads.append(download)

        def completed():
            if not download.isFinished():
                return
            success = download.state() == download.DownloadState.DownloadCompleted
            if args.self_test:
                try:
                    backup = json.loads(path.read_text(encoding="utf-8"))
                    assert backup["format"] == "huntlog-backup"
                    assert backup["hunts"] == [] and backup["prices"] == []
                    finish_test({"ok": success, "backup_download": success, "empty_diary": True})
                except Exception:
                    finish_test({"ok": False, "error": traceback.format_exc()})
            elif success:
                window.statusBar().showMessage(f"Backup salvo: {path}", 10000)
            else:
                QMessageBox.warning(window, "Backup", "Não foi possível salvar: " + download.interruptReasonString())
        download.isFinishedChanged.connect(completed)
        download.accept()

    profile.downloadRequested.connect(save_download)
    menu = window.menuBar().addMenu("Arquivo")
    for title, callback in (
        ("Backup e restauração", lambda: view.setUrl(QUrl(origin + "/#backup"))),
        ("Abrir pasta dos meus dados", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data)))),
        ("Recarregar", view.reload),
        ("Sair", window.close),
    ):
        action = QAction(title, window)
        action.triggered.connect(callback)
        menu.addAction(action)

    # Worker threads keep the window responsive during network and disk work.
    from app import APP_VERSION
    import updater
    from datetime import datetime

    class UpdateEvents(QObject):
        done = Signal(object, str, bool)

    update_events = UpdateEvents(window)
    update_action = QAction("Verificar atualizações", window)
    window.menuBar().addMenu("Atualizações").addAction(update_action)
    update_busy = [False]

    def check_updates(manual=False):
        if update_busy[0]:
            return
        update_busy[0] = True
        update_action.setEnabled(False)
        def worker():
            try:
                update_events.done.emit(updater.latest(APP_VERSION), "", manual)
            except Exception as error:
                update_events.done.emit(None, str(error), manual)
        threading.Thread(target=worker, daemon=True).start()

    def update_ready(result, error, manual):
        update_busy[0] = False
        update_action.setEnabled(True)
        if error:
            window.statusBar().showMessage("Atualizações: " + error, 15000)
            if manual:
                QMessageBox.information(window, "Atualizações", error)
            return
        if result and "stage" in result:
            try:
                backup_dir = data / "backups"
                backup_dir.mkdir(exist_ok=True)
                backup_path = backup_dir / ("antes-atualizacao-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")
                backup_path.write_text(json.dumps(DesktopHandler.store.backup(), ensure_ascii=False), encoding="utf-8")
                import sqlite3
                with DesktopHandler.store.connect() as source, sqlite3.connect(backup_path.with_suffix(".sqlite3")) as target:
                    source.backup(target)
                updater.launch_install(result["stage"], sys.executable, data, os.getpid())
                window.close()
            except Exception as failure:
                QMessageBox.warning(window, "Atualização não instalada", str(failure))
            return
        if not result:
            if manual:
                QMessageBox.information(window, "Atualizações", "Você já está usando a versão mais recente disponível.")
            return
        if not getattr(sys, "frozen", False):
            QMessageBox.information(window, "Atualizações", "A instalação pelo aplicativo está disponível no executável Windows.")
            return
        dialog = QDialog(window)
        dialog.setWindowTitle("Novidades da atualização")
        dialog.resize(640, 480)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(result["tag"] + " disponível — veja o que mudou:"))
        notes = QPlainTextEdit(dialog)
        notes.setReadOnly(True)
        notes.setPlainText(result.get("notes") or "Esta versão não possui novidades descritas.")
        layout.addWidget(notes)
        footer = QLabel("Seu diário terá um backup. O Huntlog será reiniciado após a instalação.")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        buttons = QDialogButtonBox(dialog)
        download_button = buttons.addButton("Baixar e atualizar", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("Agora não", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        update_busy[0] = True
        update_action.setEnabled(False)
        window.statusBar().showMessage("Baixando e verificando atualização. Aguarde…")
        def download_worker():
            try:
                stage = updater.download(result)
                update_events.done.emit({"stage": str(stage)}, "", True)
            except Exception as failure:
                update_events.done.emit(None, str(failure), True)
        threading.Thread(target=download_worker, daemon=True).start()

    update_events.done.connect(update_ready)
    update_action.triggered.connect(lambda: check_updates(True))
    if not args.self_test:
        QTimer.singleShot(5000, lambda: check_updates(False))
        update_result = data / "update-result.txt"
        if update_result.exists():
            message = update_result.read_text(encoding="utf-8-sig")
            update_result.unlink()
            QTimer.singleShot(1000, lambda: QMessageBox.information(window, "Atualização", message))

    if args.self_test:
        attempts = [0]
        def inspect_dom():
            page.runJavaScript("JSON.stringify({title:document.title,text:document.body.innerText,images:window.__imageTest})", check_dom)

        def check_dom(value):
            attempts[0] += 1
            try:
                state = json.loads(value)
                if "Seu próximo resultado começa aqui" not in state["text"]:
                    if attempts[0] < 40:
                        QTimer.singleShot(250, inspect_dom)
                        return
                    raise AssertionError(state["text"])
                if not state.get("images"):
                    from urllib.parse import quote
                    catalog = json.loads((root / "static/sprites/catalog.json").read_text(encoding="utf-8"))
                    by_file = {entry["file"]: name for name, entry in catalog.items() if entry.get("file")}
                    urls = ["/api/sprite?name=" + quote(name) for name in by_file.values()] + ["/favicon.svg", "/sprite-placeholder.svg"]
                    page.runJavaScript("window.__imageTest={pending:true}; (async()=>{const urls=" + json.dumps(urls) + ";const errors=[]; for(const url of urls){await new Promise(resolve=>{const image=new Image();image.onload=()=>{if(!image.naturalWidth)errors.push(url);resolve();};image.onerror=()=>{errors.push(url);resolve();};image.src=url;});}window.__imageTest={count:urls.length,errors};})()")
                    QTimer.singleShot(250, inspect_dom)
                    return
                if state["images"].get("pending"):
                    QTimer.singleShot(250, inspect_dom)
                    return
                assert not state["images"]["errors"], state["images"]["errors"]
                test_result.update(images=state["images"])
                test_result.update(page_loaded=True, title=state["title"])
                page.download(QUrl(origin + "/api/backup"), "export-test.json")
            except Exception:
                finish_test({"ok": False, "error": traceback.format_exc()})
        view.loadFinished.connect(lambda ok: QTimer.singleShot(100, inspect_dom) if ok else
                                  finish_test({"ok": False, "error": "Page failed to load"}))
        QTimer.singleShot(45000, lambda: finish_test({"ok": False, "error": "Test timeout"}))
    view.setUrl(QUrl(origin + "/"))
    window.show()
    try:
        qt.exec()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        view.setPage(QWebEnginePage(view))
        page.deleteLater()
        qt.processEvents()
        lock.unlock()
    return 0 if not args.self_test or test_result["ok"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        if "--self-test" in sys.argv:
            sys.exit(1)
        # A windowed executable must not fail silently if its files are missing.
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, "Não foi possível abrir o Huntlog. Extraia toda a pasta do ZIP antes de abrir.\n"
                                        "Detalhes: %LOCALAPPDATA%\\HuntlogDesktop\\desktop.log", "Huntlog", 0x10)
        sys.exit(1)
