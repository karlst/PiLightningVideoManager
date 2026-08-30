Pi Camera Capture packaging scaffold V1 — 2026-08-29

Copy the CONTENTS of this directory into:
    <repo>/packaging/pi/

Then from the repository root run:
    python packaging/pi/buildPiPackage.py

Output:
    dist/pi/piCameraCapture/
    dist/pi/piCameraCapture.tar.gz

This is the first clean-install/upgrade test scaffold. The new Pi should be
used to discover missing package assumptions; fixes go back into this package,
not into undocumented manual setup.
