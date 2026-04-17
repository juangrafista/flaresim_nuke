import os

try:
    from PySide2 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide6 import QtCore, QtGui, QtWidgets

from .parser import parse_lens_file, Lens
from .geometry import (
    surface_vertices,
    surface_profile,
    glass_spans,
    bounding_box,
)


class LensCrossSection(QtWidgets.QWidget):

    BG_COLOR = QtGui.QColor(245, 245, 245)
    AXIS_COLOR = QtGui.QColor(150, 150, 150)
    GLASS_FILL = QtGui.QColor(200, 215, 235, 190)
    GLASS_STROKE = QtGui.QColor(50, 60, 80)
    STOP_COLOR = QtGui.QColor(30, 30, 30)
    TEXT_COLOR = QtGui.QColor(30, 30, 30)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lens = None
        self.setMinimumSize(500, 240)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), self.BG_COLOR)
        self.setPalette(pal)

    def set_lens(self, lens):
        self._lens = lens
        self.update()

    def paintEvent(self, event):
        if self._lens is None or not self._lens.surfaces:
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        min_z, max_z, max_h = bounding_box(self._lens)
        span_z = max(max_z - min_z, 1e-6)
        span_y = max(2.0 * max_h, 1e-6)

        margin = 24
        w = self.width()
        h = self.height()
        scale = min((w - 2 * margin) / span_z, (h - 2 * margin) / span_y)
        offset_x = margin + ((w - 2 * margin) - span_z * scale) * 0.5 - min_z * scale
        offset_y = h * 0.5

        def tx(z, y):
            return QtCore.QPointF(offset_x + z * scale, offset_y - y * scale)

        pen_axis = QtGui.QPen(self.AXIS_COLOR, 1.0, QtCore.Qt.DashLine)
        painter.setPen(pen_axis)
        painter.drawLine(tx(min_z, 0.0), tx(max_z, 0.0))

        vertices = surface_vertices(self._lens)
        pen_stroke = QtGui.QPen(self.GLASS_STROKE, 1.2)
        painter.setPen(pen_stroke)
        painter.setBrush(QtGui.QBrush(self.GLASS_FILL))

        for front_idx, back_idx in glass_spans(self._lens):
            sf = self._lens.surfaces[front_idx]
            sb = self._lens.surfaces[back_idx]
            if sf.radius is None and sf.semi_aperture == 0:
                continue
            front_pts = surface_profile(sf, vertices[front_idx])
            back_pts = surface_profile(sb, vertices[back_idx])

            path = QtGui.QPainterPath()
            path.moveTo(tx(*front_pts[0]))
            for p in front_pts[1:]:
                path.lineTo(tx(*p))
            path.lineTo(tx(*back_pts[-1]))
            for p in reversed(back_pts[:-1]):
                path.lineTo(tx(*p))
            path.closeSubpath()
            painter.drawPath(path)

        pen_stop = QtGui.QPen(self.STOP_COLOR, 2.0)
        painter.setPen(pen_stop)
        for i, s in enumerate(self._lens.surfaces):
            if s.is_stop:
                z = vertices[i]
                h_ap = s.semi_aperture if s.semi_aperture > 0 else max_h * 0.5
                top = h_ap * 1.35
                painter.drawLine(tx(z, h_ap), tx(z, top))
                painter.drawLine(tx(z, -h_ap), tx(z, -top))

        painter.setPen(self.TEXT_COLOR)
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        label = self._lens.name or "(unnamed)"
        if self._lens.focal_length > 0:
            label += f"   f = {self._lens.focal_length:.1f} mm"
        if self._lens.f_number > 0:
            label += f"   f/{self._lens.f_number:g}"
        label += f"   —  {len(self._lens.surfaces)} surfaces"
        painter.drawText(12, 20, label)


class LensSectionPanel(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        top = QtWidgets.QHBoxLayout()
        self._path_edit = QtWidgets.QLineEdit()
        self._path_edit.setPlaceholderText("Path to .lens file")
        self._browse_btn = QtWidgets.QPushButton("Browse...")
        self._follow_chk = QtWidgets.QCheckBox("Follow selected FlareSim node")
        self._follow_chk.setChecked(True)
        top.addWidget(self._path_edit, 1)
        top.addWidget(self._browse_btn)
        top.addWidget(self._follow_chk)
        layout.addLayout(top)

        self._view = LensCrossSection(self)
        layout.addWidget(self._view, 1)

        self._status = QtWidgets.QLabel("")
        self._status.setStyleSheet("color: #666;")
        layout.addWidget(self._status)

        self._browse_btn.clicked.connect(self._on_browse)
        self._path_edit.editingFinished.connect(self._load_from_edit)

        self._current_path = ""
        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(500)
        self._poll_timer.timeout.connect(self._poll_selected_node)
        self._poll_timer.start()

    def _on_browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open .lens file", "", "Lens files (*.lens);;All files (*.*)"
        )
        if path:
            self._follow_chk.setChecked(False)
            self._path_edit.setText(path)
            self._load_path(path)

    def _load_from_edit(self):
        path = self._path_edit.text().strip()
        if path:
            self._follow_chk.setChecked(False)
            self._load_path(path)

    def _load_path(self, path):
        if path == self._current_path:
            return
        if not os.path.isfile(path):
            self._status.setText(f"Not found: {path}")
            return
        try:
            lens = parse_lens_file(path)
        except Exception as e:
            self._status.setText(f"Parse error: {e}")
            return
        self._current_path = path
        self._view.set_lens(lens)
        self._status.setText(f"Loaded: {os.path.basename(path)}")

    def _poll_selected_node(self):
        if not self._follow_chk.isChecked():
            return
        try:
            import nuke
        except ImportError:
            return

        nodes = nuke.selectedNodes("FlareSim")
        if not nodes:
            all_fs = nuke.allNodes("FlareSim")
            if len(all_fs) == 1:
                nodes = all_fs
        if not nodes:
            return

        try:
            path = nodes[0]["lens_file"].value()
        except Exception:
            return
        if path and path != self._current_path:
            self._path_edit.setText(path)
            self._load_path(path)
