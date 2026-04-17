"""
FlareSim_LensSection.py — Dockable 2D lens cross-section viewer.

Place this file in the same directory as FlareSim.dll on your NUKE_PATH,
next to FlareSim_LensBrowser.py. Open the panel from the Pane menu:
"FlareSim Lens Cross-Section".
"""

import nuke
import nukescripts


PANEL_ID = "uk.co.flaresim.lenssection"
PANEL_TITLE = "FlareSim Lens Cross-Section"
WIDGET_PATH = "lens_section.viewer.LensSectionPanel"


def register():
    nukescripts.panels.registerWidgetAsPanel(WIDGET_PATH, PANEL_TITLE, PANEL_ID)
    nuke.menu("Pane").addCommand(
        PANEL_TITLE,
        lambda: nukescripts.restorePanel(PANEL_ID),
    )
