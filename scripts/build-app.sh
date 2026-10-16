#!/bin/bash
# Builds dist/MacX.app (and a .dmg with --dmg) from app/ + build/engine-kit.
#   scripts/build-engine-kit.sh   first (once per Wine version)
#   scripts/build-app.sh [--dmg] [--install]
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
B="$REPO/build"; DIST="$REPO/dist"; APP="$DIST/MacX.app"
VERSION="$(cat "$REPO/VERSION" 2>/dev/null || echo 0.1.0)"
[ -f "$B/engine-kit/WINE_VERSION" ] || { echo "Run scripts/build-engine-kit.sh first."; exit 1; }

mkdir -p "$B" "$DIST"
if [ ! -f "$B/AppIcon.icns" ]; then
  swift "$REPO/app/make-icon.swift" "$B" >/dev/null
  iconutil -c icns "$B/AppIcon.iconset" -o "$B/AppIcon.icns"
fi
swiftc -O -swift-version 5 -parse-as-library -target arm64-apple-macos14 "$REPO/app/main.swift" -o "$B/MacX"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$B/MacX" "$APP/Contents/MacOS/"
cp "$REPO/app/macxctl.py" "$REPO/app/macxinstall.py" "$REPO/app/macxbox.py" "$B/AppIcon.icns" "$APP/Contents/Resources/"
cp -R "$B/engine-kit" "$APP/Contents/Resources/engine-kit"
sed "s/<string>1.0<\/string>/<string>$VERSION<\/string>/" "$REPO/app/Info.plist" > "$APP/Contents/Info.plist"
cp "$REPO/LICENSE" "$REPO/THIRD_PARTY_NOTICES.md" "$APP/Contents/Resources/" 2>/dev/null || true
codesign --force --deep --sign - "$APP" >/dev/null
echo "Built $APP ($VERSION)"

if [[ " $* " == *" --dmg "* ]]; then
  DMG="$DIST/MacX-$VERSION.dmg"; STAGE="$B/dmg"
  rm -rf "$STAGE" "$DMG"; mkdir -p "$STAGE"
  cp -R "$APP" "$STAGE/"; ln -s /Applications "$STAGE/Applications"
  hdiutil create -volname "MacX $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
  echo "Built $DMG ($(du -h "$DMG" | cut -f1))"
fi
if [[ " $* " == *" --install "* ]]; then
  rm -rf "$HOME/Applications/MacX.app"; cp -R "$APP" "$HOME/Applications/"
  /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$HOME/Applications/MacX.app"
  echo "Installed to ~/Applications"
fi
