import sys
import os
import fitz
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QScrollArea, 
                             QFileDialog, QMessageBox, QMenu, QAction, QProgressDialog)
from PyQt5.QtCore import Qt, QMimeData, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage, QDrag, QPainter, QCursor
from PIL import Image


class PdfLoader(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path

    def run(self):
        try:
            doc = fitz.open(self.file_path)
            pages = []
            total = len(doc)
            for page_num in range(total):
                page = doc[page_num]
                scale = 300 / 72
                mat = fitz.Matrix(scale, scale)
                pix = page.get_pixmap(matrix=mat)
                pages.append((page_num, pix))
                self.progress.emit(page_num + 1, total)
            doc.close()
            self.finished.emit(pages)
        except Exception as e:
            self.error.emit(str(e))


class PageThumbnail(QLabel):
    def __init__(self, page_num, pixmap, main_window, parent=None):
        super().__init__(parent)
        self.page_num = page_num
        self.original_pixmap = pixmap
        self.main_window = main_window
        self.setPixmap(pixmap.scaled(150, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("border: 2px solid transparent; padding: 5px;")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.is_selected = False
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_selection()
        super().mousePressEvent(event)

    def toggle_selection(self):
        self.is_selected = not self.is_selected
        if self.is_selected:
            self.setStyleSheet("border: 2px solid #0078D4; padding: 5px; background-color: #E3F2FD;")
        else:
            self.setStyleSheet("border: 2px solid transparent; padding: 5px;")
        self.main_window.on_page_clicked(self.page_num, self.is_selected)

    def show_context_menu(self, pos):
        if self.is_selected:
            menu = QMenu(self)
            export_action = QAction("导出为 PNG", self)
            export_action.triggered.connect(self.main_window.export_selected_pages)
            menu.addAction(export_action)
            menu.exec_(self.mapToGlobal(pos))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.selected_pages = set()
        self.page_pixmaps = {}  # 存储原始高分辨率 pixmap
        self.thumbnail_pixmaps = {}  # 存储缩略图
        self.pdf_document = None
        self.current_pdf_path = None
        self.pdf_loader = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("PDF 拆分导出工具")
        self.setGeometry(100, 100, 900, 700)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # 顶部按钮区域
        btn_layout = QHBoxLayout()
        self.upload_btn = QPushButton("上传 PDF 文件")
        self.upload_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D4;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #106EBE;
            }
        """)
        self.upload_btn.clicked.connect(self.upload_pdf)
        btn_layout.addWidget(self.upload_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 状态标签
        self.status_label = QLabel("请上传 PDF 文件")
        self.status_label.setStyleSheet("color: #666; padding: 10px;")
        layout.addWidget(self.status_label)

        # 滚动区域显示页面缩略图
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background-color: #F5F5F5;")
        
        self.thumbnail_container = QWidget()
        self.thumbnail_layout = QVBoxLayout(self.thumbnail_container)
        self.scroll_area.setWidget(self.thumbnail_container)
        layout.addWidget(self.scroll_area)

    def upload_pdf(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择 PDF 文件", "", "PDF 文件 (*.pdf)"
        )
        if file_path:
            self.load_pdf(file_path)

    def load_pdf(self, file_path):
        try:
            self.current_pdf_path = file_path
            self.selected_pages.clear()
            self.page_pixmaps.clear()
            self.thumbnail_pixmaps.clear()

            # 清除旧内容
            while self.thumbnail_layout.count():
                item = self.thumbnail_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            self.status_label.setText("正在加载 PDF...")
            self.upload_btn.setEnabled(False)

            # 使用线程加载 PDF
            self.pdf_loader = PdfLoader(file_path)
            self.pdf_loader.progress.connect(self.on_load_progress)
            self.pdf_loader.finished.connect(self.on_load_finished)
            self.pdf_loader.error.connect(self.on_load_error)
            self.pdf_loader.start()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载 PDF 失败: {str(e)}")

    def on_load_progress(self, current, total):
        self.status_label.setText(f"正在加载: {current}/{total} 页")

    def on_load_finished(self, pages):
        self.page_pixmaps.clear()
        self.thumbnail_pixmaps.clear()
        
        for page_num, pix in pages:
            # 转换为 QPixmap (原始分辨率)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(img)
            self.page_pixmaps[page_num] = pixmap
            
            # 创建缩略图
            thumbnail_pixmap = pixmap.scaled(150, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.thumbnail_pixmaps[page_num] = thumbnail_pixmap
            
            thumbnail = PageThumbnail(page_num, thumbnail_pixmap, self)
            self.thumbnail_layout.addWidget(thumbnail)

        self.status_label.setText(f"已加载: {os.path.basename(self.current_pdf_path)}，共 {len(pages)} 页")
        self.upload_btn.setEnabled(True)

    def on_load_error(self, error_msg):
        self.status_label.setText("加载失败")
        self.upload_btn.setEnabled(True)
        QMessageBox.critical(self, "错误", f"加载 PDF 失败: {error_msg}")

    def on_page_clicked(self, page_num, is_selected):
        if is_selected:
            self.selected_pages.add(page_num)
        else:
            self.selected_pages.discard(page_num)
        
        count = len(self.selected_pages)
        if count > 0:
            self.status_label.setText(f"已选择 {count} 页，右键点击可导出")
        else:
            self.status_label.setText("请选择页面")

    def export_selected_pages(self):
        if not self.selected_pages:
            return

        output_dir = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if not output_dir:
            return

        try:
            pdf_name = os.path.splitext(os.path.basename(self.current_pdf_path))[0]
            exported_count = 0

            for page_num in sorted(self.selected_pages):
                # 直接使用 PyMuPDF 重新渲染页面，避免 PyQt5 转换问题
                doc = fitz.open(self.current_pdf_path)
                page = doc[page_num]
                scale = 300 / 72
                mat = fitz.Matrix(scale, scale)
                pix = page.get_pixmap(matrix=mat)
                
                # 直接从 PyMuPDF 保存为 PNG
                output_path = os.path.join(output_dir, f"{pdf_name}_page_{page_num + 1}.png")
                pix.save(output_path)
                doc.close()
                exported_count += 1

            QMessageBox.information(self, "完成", f"已成功导出 {exported_count} 张图片到:\n{output_dir}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {str(e)}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
