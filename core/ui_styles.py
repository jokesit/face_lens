"""Qt stylesheet constants for FaceLens."""

STYLESHEET = """
QMainWindow { background-color: #F5F7FA; }
QLabel#TitleLabel { font-size: 26px; font-weight: 800; color: #1F618D; padding: 0px; }
QLabel#SubtitleLabel { font-size: 12px; color: #566573; padding-bottom: 2px; }
QLabel#CameraLabel { background-color: #FFFFFF; border: 1px solid #E0E0E0; border-radius: 10px; }
QWidget#ControlsPanel { background-color: #FFFFFF; border: 1px solid #E5E8E8; border-radius: 10px; }
QToolButton#ControlsToggleButton { background-color: #EAF2F8; color: #1F618D; font-size: 12px; font-weight: 700; padding: 5px 14px; border: 1px solid #AED6F1; border-radius: 14px; }
QToolButton#ControlsToggleButton:hover { background-color: #D6EAF8; border-color: #3498DB; }
QLabel#NameLabel { font-size: 20px; font-weight: 800; padding: 8px; border-radius: 8px; }
QLabel#StatusLabel { font-size: 12px; color: #566573; padding: 2px; }
QLabel#PerformanceHintLabel { font-size: 11px; color: #5D6D7E; padding: 2px; }
QLabel#ConfidenceHintLabel { font-size: 11px; color: #5D6D7E; padding: 2px; }
QComboBox { background-color: #FFFFFF; color: #1F2D3D; font-size: 12px; padding: 5px 8px; border: 1px solid #D5DBDB; border-radius: 7px; min-width: 150px; min-height: 24px; }
QComboBox:hover { border-color: #3498DB; }
QPushButton { background-color: #3498DB; color: white; font-size: 12px; font-weight: 700; padding: 7px 10px; border-radius: 7px; border: none; min-height: 24px; }
QPushButton:hover { background-color: #2980B9; }
QPushButton:pressed { background-color: #1F618D; }
QCheckBox { color: #566573; font-size: 12px; padding: 3px; }
QStatusBar { color: #566573; font-size: 11px; background-color: #F5F7FA; }
"""
