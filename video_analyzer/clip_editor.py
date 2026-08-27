"""Entry point: python -m video_analyzer.clip_editor [folder|capture.mp4|capture.json]"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from common.candidate_config import CANDIDATE_CONFIG
from video_analyzer.capture_data import load_capture
from video_analyzer.candidate_replay import replay_candidate_finder
from video_analyzer.solution_config import SOLUTION_CONFIG, solution_config_for_sensitivity
from video_analyzer.solution_filter import SolutionFilter, failed_candidate_result
from video_analyzer.clip_editor_window import ClipEditorWindow

def classify_capture(path: Path):
    cd=load_capture(path); cr=replay_candidate_finder(cd,CANDIDATE_CONFIG)
    sc=solution_config_for_sensitivity(CANDIDATE_CONFIG.sensitivity,SOLUTION_CONFIG)
    sr=failed_candidate_result() if cr.frame_index is None else SolutionFilter(sc).evaluate(cd.pi_brightness,cd.pi_brightness_delta,cr.frame_index,cr.reason)
    return cd,cr,sr

def main():
    ap=argparse.ArgumentParser(description="Edit capture sidecar metadata")
    ap.add_argument("path",nargs="?",type=Path,default=None,help="Optional folder or capture MP4/JSON")
    args=ap.parse_args(); app=QApplication(sys.argv)
    p=args.path.expanduser() if args.path is not None else None
    try:
        if p is None:
            w=ClipEditorWindow(None,None,None,open_directory=Path.cwd())
        elif p.is_dir():
            clips=sorted((x for x in p.iterdir() if x.is_file() and x.suffix.lower()==".mp4"),key=lambda x:x.name.lower())
            if clips:
                cd,cr,sr=classify_capture(clips[0]); w=ClipEditorWindow(cd,cr,sr,open_directory=p)
            else:
                w=ClipEditorWindow(None,None,None,open_directory=p)
        else:
            cd,cr,sr=classify_capture(p); w=ClipEditorWindow(cd,cr,sr,open_directory=cd.video_path.parent)
    except (RuntimeError,OSError) as e:
        print(f"Clip Editor: {e}",file=sys.stderr); return 1
    w.show(); return app.exec()

if __name__=="__main__": raise SystemExit(main())
