"""Clip Editor: human-curated sidecar metadata editor sharing Analyzer components."""
from __future__ import annotations
import copy, json
from pathlib import Path
from typing import Any
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (QComboBox,QDoubleSpinBox,QGridLayout,QGroupBox,QHBoxLayout,QLabel,QLineEdit,QListWidget,QListWidgetItem,QMainWindow,QMessageBox,QPushButton,QSlider,QTextEdit,QVBoxLayout,QWidget)
from common.candidate_config import CANDIDATE_CONFIG
from video_analyzer.analyzer_window import AnalyzerWindow
from video_analyzer.capture_data import load_capture
from video_analyzer.candidate_replay import replay_candidate_finder
from video_analyzer.graph_panel import GraphPanel
from video_analyzer.solution_config import SOLUTION_CONFIG, solution_config_for_sensitivity
from video_analyzer.solution_filter import SolutionFilter, failed_candidate_result
from video_analyzer.solution_panel import SolutionPanel
from video_analyzer.video_reader import VideoReader

CLASSIFICATIONS=("---","IC","CG","LCC")

def nested(sidecar, key, legacy=None, default=None):
    camera=sidecar.get("camera",{}) if isinstance(sidecar,dict) else {}
    if isinstance(camera,dict) and key in camera: return camera.get(key,default)
    return sidecar.get(legacy or key,default) if isinstance(sidecar,dict) else default

class ClipEditorWindow(AnalyzerWindow):
    def __init__(self,capture_data,candidate_result,solution_result,open_directory=None):
        self.loaded_metadata={}
        if capture_data is not None:
            super().__init__(capture_data,candidate_result,solution_result)
            if open_directory is not None:
                self.open_directory=Path(open_directory); self.refresh_file_browser()
            self.setWindowTitle("Clip Editor"); self.load_editor_fields(); self.focus_description_at_end()
            return
        QMainWindow.__init__(self)
        self.capture_data=None; self.candidate_result=None; self.solution_result=None
        self.candidate_config=CANDIDATE_CONFIG; self.frame_number=0; self.updating_slider=False
        self.open_directory=Path(open_directory or Path.cwd()); self.video_reader=None
        self.setWindowTitle("Clip Editor"); self.resize(1500,875)
        self.create_ui(); self.connect_controls(); self.set_editor_enabled(False)

    # Analyzer calls these; Clip Editor intentionally has no capture/current-frame text panels.
    def update_capture_information(self): pass
    def update_frame_information(self): pass

    def spin(self,lo,hi,decimals):
        w=QDoubleSpinBox(); w.setRange(lo,hi); w.setDecimals(decimals); w.setKeyboardTracking(False); return w

    def create_ui(self):
        central=QWidget(); self.setCentralWidget(central)
        main=QVBoxLayout(central); main.setContentsMargins(6,6,6,6); main.setSpacing(4)
        grid=QGridLayout(); grid.setHorizontalSpacing(6); grid.setVerticalSpacing(6)
        grid.setColumnStretch(0,0); grid.setColumnStretch(1,7); grid.setColumnStretch(2,3)
        grid.setRowStretch(0,3); grid.setRowStretch(1,2)

        browser=QGroupBox("Captures"); browser.setMinimumWidth(220); browser.setMaximumWidth(280)
        bl=QVBoxLayout(browser); self.directory_label=QLabel(); self.directory_label.setWordWrap(True)
        self.directory_label.setStyleSheet("QLabel { color: #555; font-size: 10px; }")
        self.file_list=QListWidget(); self.file_list.setAlternatingRowColors(True)
        bb=QHBoxLayout(); self.parent_folder_button=QPushButton("Up"); self.open_browser_button=QPushButton("Open")
        bb.addWidget(self.parent_folder_button); bb.addWidget(self.open_browser_button)
        bl.addWidget(self.directory_label); bl.addWidget(self.file_list,1); bl.addLayout(bb); grid.addWidget(browser,0,0,2,1)

        self.image_label=QLabel(); self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.image_label.setMinimumHeight(240)
        self.image_label.setStyleSheet("QLabel { background-color: black; }"); grid.addWidget(self.image_label,0,1)
        if self.capture_data is not None:
            self.graph_panel=GraphPanel(self.capture_data,self.candidate_result,self.candidate_config); grid.addWidget(self.graph_panel,1,1)
        else:
            self.graph_panel=None; empty=QLabel("Select a clip to load"); empty.setAlignment(Qt.AlignmentFlag.AlignCenter); grid.addWidget(empty,1,1)

        right=QWidget(); rl=QVBoxLayout(right); rl.setContentsMargins(0,0,0,0); rl.setSpacing(4)
        edit=QGroupBox("Clip metadata"); el=QGridLayout(edit)
        self.site_edit=QLineEdit(); self.latitude_spin=self.spin(-90,90,7); self.longitude_spin=self.spin(-180,180,7)
        self.bearing_spin=self.spin(0,359.999,3); self.hfov_spin=self.spin(1,120,3); self.vfov_spin=self.spin(1,120,3)
        self.classification_combo=QComboBox(); self.classification_combo.addItems(CLASSIFICATIONS)
        self.description_edit=QTextEdit(); self.description_edit.setAcceptRichText(False); self.description_edit.setMinimumHeight(120)
        rows=[("Site name",self.site_edit),("Latitude",self.latitude_spin),("Longitude",self.longitude_spin),("Bearing",self.bearing_spin),("Horizontal FOV",self.hfov_spin),("Vertical FOV",self.vfov_spin),("Classification",self.classification_combo)]
        for r,(name,w) in enumerate(rows): el.addWidget(QLabel(name+":"),r,0); el.addWidget(w,r,1)
        r=len(rows); el.addWidget(QLabel("Description:"),r,0,Qt.AlignmentFlag.AlignTop); el.addWidget(self.description_edit,r,1)
        buttons=QHBoxLayout(); self.restore_button=QPushButton("Restore"); self.save_button=QPushButton("Save Changes")
        self.save_button.setDefault(True); self.save_button.setAutoDefault(True)
        buttons.addWidget(self.restore_button); buttons.addWidget(self.save_button); el.addLayout(buttons,r+1,0,1,2); el.setColumnStretch(1,1)
        rl.addWidget(edit)
        analysis=QGroupBox("Analysis"); al=QGridLayout(analysis); self.sensitivity_value=QLabel(self.candidate_config.sensitivity.capitalize())
        al.addWidget(QLabel("Sensitivity:"),0,0); al.addWidget(self.sensitivity_value,0,1); rl.addWidget(analysis)
        if self.solution_result is not None:
            self.solution_panel=SolutionPanel(self.solution_result); rl.addWidget(self.solution_panel)
        else: self.solution_panel=None
        rl.addStretch(1); grid.addWidget(right,0,2,2,1)
        self.refresh_file_browser(); main.addLayout(grid,1)

        shortcut_label=QLabel("Ctrl+Left/Right: Previous/Next clip    Ctrl+Enter: Save + Next clip    Left/Right: Previous/Next frame    Enter: Save    Esc: Restore")
        shortcut_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shortcut_label.setStyleSheet("QLabel { color: #555; font-size: 10px; }")
        main.addWidget(shortcut_label)

        controls=QHBoxLayout(); self.first_button=QPushButton("|<"); self.previous_button=QPushButton("<"); self.next_button=QPushButton(">"); self.last_button=QPushButton(">|")
        frame_count=self.capture_data.frame_count if self.capture_data is not None else 0
        self.frame_slider=QSlider(Qt.Orientation.Horizontal); self.frame_slider.setRange(0,max(0,frame_count-1)); self.frame_slider.setSingleStep(1); self.frame_slider.setPageStep(10)
        self.slider_frame_label=QLabel(f"0 / {max(0,frame_count-1)}"); self.slider_frame_label.setMinimumWidth(100)
        for w in (self.first_button,self.previous_button): controls.addWidget(w)
        controls.addWidget(self.frame_slider,1); controls.addWidget(self.slider_frame_label); controls.addWidget(self.next_button); controls.addWidget(self.last_button); main.addLayout(controls)

    def connect_controls(self):
        self.parent_folder_button.clicked.connect(self.browse_parent_directory); self.open_browser_button.clicked.connect(self.open_selected_browser_item)
        self.file_list.itemDoubleClicked.connect(lambda _i:self.open_selected_browser_item())
        self.first_button.clicked.connect(lambda:self.set_frame(0)); self.previous_button.clicked.connect(lambda:self.set_frame(self.frame_number-1)); self.next_button.clicked.connect(lambda:self.set_frame(self.frame_number+1)); self.last_button.clicked.connect(lambda:self.set_frame(self.capture_data.frame_count-1 if self.capture_data is not None else 0)); self.frame_slider.valueChanged.connect(self.on_slider_changed)
        self.restore_button.clicked.connect(self.restore_loaded_values); self.save_button.clicked.connect(self.save_changes)
        self.setTabOrder(self.site_edit,self.latitude_spin); self.setTabOrder(self.latitude_spin,self.longitude_spin)
        self.setTabOrder(self.longitude_spin,self.bearing_spin); self.setTabOrder(self.bearing_spin,self.hfov_spin)
        self.setTabOrder(self.hfov_spin,self.vfov_spin); self.setTabOrder(self.vfov_spin,self.classification_combo)
        self.setTabOrder(self.classification_combo,self.description_edit)

        # Metadata keyboard navigation is deliberately independent of the
        # buttons and of QTextEdit's normal Tab/Enter behavior.
        self._editor_fields=(self.site_edit,self.latitude_spin,self.longitude_spin,self.bearing_spin,self.hfov_spin,self.vfov_spin,self.classification_combo,self.description_edit)
        for field in self._editor_fields:
            field.installEventFilter(self)
            for child in field.findChildren(QWidget):
                child.installEventFilter(self)

    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.KeyPress and self._is_editor_object(obj):
            key=event.key(); modifiers=event.modifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                if key==Qt.Key.Key_Left:
                    self.load_adjacent_clip(-1)
                    return True
                if key==Qt.Key.Key_Right:
                    self.load_adjacent_clip(1)
                    return True
                if key in (Qt.Key.Key_Return,Qt.Key.Key_Enter):
                    self.save_and_next_clip()
                    return True
            if key in (Qt.Key.Key_Return,Qt.Key.Key_Enter):
                if self._field_for_object(obj) is self.description_edit and modifiers & Qt.KeyboardModifier.ShiftModifier:
                    self.description_edit.insertPlainText("\n")
                else:
                    self.save_button.click()
                return True
            if key==Qt.Key.Key_Escape:
                self.restore_button.click()
                return True
            if key in (Qt.Key.Key_Tab,Qt.Key.Key_Backtab):
                backwards=(key==Qt.Key.Key_Backtab) or bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
                self._move_editor_focus(obj,-1 if backwards else 1)
                return True
        return super().eventFilter(obj,event)

    def _field_for_object(self,obj):
        for field in getattr(self,"_editor_fields",()):
            if obj is field or field.isAncestorOf(obj): return field
        return None

    def _is_editor_object(self,obj):
        return self._field_for_object(obj) is not None

    def _move_editor_focus(self,obj,direction):
        fields=getattr(self,"_editor_fields",())
        current=self._field_for_object(obj)
        if not fields or current is None: return
        index=fields.index(current)
        for step in range(1,len(fields)+1):
            target=fields[(index+direction*step)%len(fields)]
            if target.isEnabled() and target.focusPolicy()!=Qt.FocusPolicy.NoFocus:
                target.setFocus(Qt.FocusReason.BacktabFocusReason if direction<0 else Qt.FocusReason.TabFocusReason)
                return

    def adjacent_clip_path(self,direction):
        if self.capture_data is None:
            return None
        clips=sorted(
            (p for p in self.open_directory.iterdir() if p.is_file() and p.suffix.lower()==".mp4"),
            key=lambda p:p.name.lower(),
        )
        if not clips:
            return None
        try:
            current=self.capture_data.video_path.resolve()
            index=next(i for i,p in enumerate(clips) if p.resolve()==current)
        except (OSError,StopIteration):
            return None
        target=index+direction
        if target<0 or target>=len(clips):
            return None
        return clips[target]

    def load_adjacent_clip(self,direction):
        target=self.adjacent_clip_path(direction)
        if target is not None:
            self.load_new_capture(target)

    def save_and_next_clip(self):
        target=self.adjacent_clip_path(1)

        # Ctrl+Enter is a workflow command, not an unconditional Save click.
        # If this clip is clean, advance immediately without a save prompt.
        # If it is dirty, save first; Cancel leaves the current clip loaded.
        if self.has_unsaved_changes():
            if not self.save_changes():
                return

        if target is not None:
            self.load_new_capture(target)

    def set_editor_enabled(self,enabled):
        for w in (self.site_edit,self.latitude_spin,self.longitude_spin,self.bearing_spin,self.hfov_spin,self.vfov_spin,self.classification_combo,self.description_edit,self.restore_button,self.save_button): w.setEnabled(enabled)

    def focus_description_at_end(self):
        if not self.description_edit.isEnabled(): return
        self.description_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        cursor=self.description_edit.textCursor(); cursor.movePosition(cursor.MoveOperation.End); self.description_edit.setTextCursor(cursor)

    def metadata(self):
        s=(self.capture_data.sidecar if self.capture_data is not None else None) or {}; c=str(s.get("classification","") or "").upper(); c=c if c in CLASSIFICATIONS[1:] else "---"
        return dict(site_name=nested(s,"site_name","site_name","") or "",latitude=float(nested(s,"latitude_degrees","camera_latitude_degrees",0) or 0),longitude=float(nested(s,"longitude_degrees","camera_longitude_degrees",0) or 0),bearing=float(nested(s,"bearing_degrees","camera_bearing_degrees",0) or 0),hfov=float(nested(s,"hfov_degrees","camera_hfov_degrees",1) or 1),vfov=float(nested(s,"vfov_degrees","camera_vfov_degrees",1) or 1),classification=c,description=str(s.get("description","") or ""))

    def current_values(self):
        return dict(site_name=self.site_edit.text().strip(),latitude=self.latitude_spin.value(),longitude=self.longitude_spin.value(),bearing=self.bearing_spin.value(),hfov=self.hfov_spin.value(),vfov=self.vfov_spin.value(),classification=self.classification_combo.currentText(),description=self.description_edit.toPlainText())

    def load_editor_fields(self):
        enabled=self.capture_data is not None and self.capture_data.sidecar is not None
        self.set_editor_enabled(enabled)
        if not enabled: self.loaded_metadata={}; return
        self.loaded_metadata=copy.deepcopy(self.metadata()); self.restore_loaded_values()

    def restore_loaded_values(self):
        if not self.loaded_metadata:return
        v=self.loaded_metadata; self.site_edit.setText(v["site_name"]); self.latitude_spin.setValue(v["latitude"]); self.longitude_spin.setValue(v["longitude"]); self.bearing_spin.setValue(v["bearing"]); self.hfov_spin.setValue(v["hfov"]); self.vfov_spin.setValue(v["vfov"])
        self.classification_combo.setCurrentText(v["classification"]); self.description_edit.setPlainText(v["description"])

    def has_unsaved_changes(self): return bool(self.loaded_metadata) and self.current_values()!=self.loaded_metadata

    def save_changes(self):
        if self.capture_data is None or self.capture_data.sidecar is None:return False
        p=self.capture_data.sidecar_path
        if QMessageBox.question(self,"Save Changes",f"Save changes to {p.name}?",QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Save:return False
        v=self.current_values(); s=copy.deepcopy(self.capture_data.sidecar); cam=s.setdefault("camera",{})
        cam.update(site_name=v["site_name"],latitude_degrees=v["latitude"],longitude_degrees=v["longitude"],bearing_degrees=v["bearing"],hfov_degrees=v["hfov"],vfov_degrees=v["vfov"])
        s["classification"]="" if v["classification"]=="---" else v["classification"]; s["description"]=v["description"]
        tmp=p.with_suffix(".json.tmp")
        try: tmp.write_text(json.dumps(s,indent=4)+"\n",encoding="utf-8"); tmp.replace(p)
        except OSError as e: QMessageBox.critical(self,"Unable to save sidecar",str(e)); return False
        self.capture_data.sidecar=s; self.loaded_metadata=copy.deepcopy(v); return True

    def confirm_abandon_changes(self):
        if not self.has_unsaved_changes():return True
        box=QMessageBox(self); box.setWindowTitle("Unsaved changes"); box.setText("This clip has unsaved changes."); box.setInformativeText("Save the changes before continuing?")
        save=box.addButton("Save",QMessageBox.ButtonRole.AcceptRole); discard=box.addButton("Discard",QMessageBox.ButtonRole.DestructiveRole); cancel=box.addButton("Cancel",QMessageBox.ButtonRole.RejectRole); box.exec()
        if box.clickedButton() is save:return self.save_changes()
        if box.clickedButton() is discard:return True
        return False

    def refresh_file_browser(self):
        if not hasattr(self,"file_list"): return
        self.directory_label.setText(str(self.open_directory)); self.file_list.clear()
        try: entries=sorted(self.open_directory.iterdir(),key=lambda p:(not p.is_dir(),p.name.lower()))
        except OSError as e: QMessageBox.warning(self,"Unable to read folder",str(e)); return
        current=None
        if self.capture_data is not None:
            try: current=self.capture_data.video_path.resolve()
            except OSError: pass
        selected=None
        for p in entries:
            if not p.is_dir() and p.suffix.lower()!=".mp4": continue
            item=QListWidgetItem(f"[Folder] {p.name}" if p.is_dir() else p.name); item.setData(Qt.ItemDataRole.UserRole,str(p)); self.file_list.addItem(item)
            if current is not None:
                try:
                    if p.resolve()==current: selected=item
                except OSError: pass
        if selected is not None: self.file_list.setCurrentItem(selected); self.file_list.scrollToItem(selected)

    def open_selected_browser_item(self):
        item=self.file_list.currentItem()
        if item is None:return
        p=Path(item.data(Qt.ItemDataRole.UserRole))
        if p.is_dir():
            if self.confirm_abandon_changes(): self.open_directory=p; self.refresh_file_browser()
        elif p.suffix.lower()==".mp4": self.load_new_capture(p)

    def browse_parent_directory(self):
        parent=self.open_directory.parent
        if parent!=self.open_directory and self.confirm_abandon_changes(): self.open_directory=parent; self.refresh_file_browser()

    def load_new_capture(self,video_path):
        if not self.confirm_abandon_changes():return
        try:
            cd=load_capture(video_path); cr=replay_candidate_finder(cd,self.candidate_config); sc=solution_config_for_sensitivity(self.candidate_config.sensitivity,SOLUTION_CONFIG)
            sr=failed_candidate_result() if cr.frame_index is None else SolutionFilter(sc).evaluate(cd.pi_brightness,cd.pi_brightness_delta,cr.frame_index,cr.reason); vr=VideoReader(cd.video_path)
        except RuntimeError as e: QMessageBox.critical(self,"Unable to open capture",str(e)); return
        if self.video_reader is not None: self.video_reader.close()
        self.capture_data=cd; self.candidate_result=cr; self.solution_result=sr; self.video_reader=vr; self.open_directory=cd.video_path.parent; self.frame_number=0; self.updating_slider=False
        self.create_ui(); self.connect_controls(); self.load_editor_fields(); self.set_frame(0,force=True); self.focus_description_at_end()

    def set_frame(self,frame_number,force=False):
        if self.capture_data is None or self.video_reader is None: return
        return super().set_frame(frame_number,force)

    def resizeEvent(self,event):
        if self.capture_data is None or self.video_reader is None:
            QMainWindow.resizeEvent(self,event); return
        super().resizeEvent(event)

    def closeEvent(self,event:QCloseEvent):
        if not self.confirm_abandon_changes(): event.ignore(); return
        if self.video_reader is not None: self.video_reader.close()
        event.accept()
