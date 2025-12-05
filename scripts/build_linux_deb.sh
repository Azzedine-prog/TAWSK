#!/usr/bin/env bash
set -euo pipefail

# Build Debian package for Study Tracker
# Requires: dpkg-deb, python3, pip, pyinstaller (for bundling optional)

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$PROJECT_ROOT"
VERSION=$(python - <<'PY'
from tracker_app.tracker import __version__
print(__version__)
PY
)
BUILD_DIR="$PROJECT_ROOT/build/deb"
DIST_DIR="$PROJECT_ROOT/dist/deb"
mkdir -p "$BUILD_DIR/DEBIAN" "$BUILD_DIR/usr/bin" "$BUILD_DIR/usr/share/applications" "$BUILD_DIR/usr/share/icons/hicolor/128x128/apps" "$DIST_DIR"

# Launcher script
cat > "$BUILD_DIR/usr/bin/study-tracker" <<'EOF'
#!/usr/bin/env bash
python3 /usr/share/study-tracker/tracker_app/main.py "$@"
EOF
chmod +x "$BUILD_DIR/usr/bin/study-tracker"

# Install application files
mkdir -p "$BUILD_DIR/usr/share/study-tracker"
cp -r "$PROJECT_ROOT/tracker_app" "$BUILD_DIR/usr/share/study-tracker/"
cp "$PROJECT_ROOT/resources/icons/app.svg" "$BUILD_DIR/usr/share/icons/hicolor/128x128/apps/study-tracker.svg"

# Desktop entry
cat > "$BUILD_DIR/usr/share/applications/study-tracker.desktop" <<EOF
[Desktop Entry]
Version=$VERSION
Type=Application
Name=Study Tracker
Exec=study-tracker
Icon=study-tracker
Terminal=false
Categories=Utility;
EOF

# Control file
cat > "$BUILD_DIR/DEBIAN/control" <<EOF
Package: study-tracker
Version: $VERSION
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Study Tracker Team <maintainer@example.com>
Description: Daily study/work tracker with timers and reporting.
EOF

dpkg-deb --build "$BUILD_DIR" "$DIST_DIR/study-tracker_${VERSION}_amd64.deb"
echo "Debian package created at $DIST_DIR"
