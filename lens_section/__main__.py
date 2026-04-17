import sys

try:
    from PySide2 import QtWidgets
except ImportError:
    from PySide6 import QtWidgets

from .viewer import LensSectionPanel


def main():
    app = QtWidgets.QApplication(sys.argv)
    panel = LensSectionPanel()
    panel._follow_chk.setChecked(False)
    panel._follow_chk.setVisible(False)
    panel.resize(1100, 520)
    panel.setWindowTitle("Lens Cross-Section (standalone)")
    if len(sys.argv) > 1:
        panel._path_edit.setText(sys.argv[1])
        panel._load_path(sys.argv[1])
    panel.show()
    sys.exit(app.exec_() if hasattr(app, "exec_") else app.exec())


if __name__ == "__main__":
    main()
