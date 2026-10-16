// Draws the MacX app icon: two offset window grids on a blue tile.
import AppKit
let out = CommandLine.arguments[1]
let s: CGFloat = 1024
let img = NSImage(size: NSSize(width: s, height: s))
img.lockFocus()
let tile = NSBezierPath(roundedRect: NSRect(x: 100, y: 100, width: 824, height: 824), xRadius: 185, yRadius: 185)
NSGradient(colors: [NSColor(red: 0.05, green: 0.36, blue: 0.95, alpha: 1), NSColor(red: 0.35, green: 0.18, blue: 0.85, alpha: 1)])!
    .draw(in: tile, angle: -60)
func grid(_ x: CGFloat, _ y: CGFloat, _ size: CGFloat, _ color: NSColor) {
    let g: CGFloat = size * 0.06, p = (size - g) / 2
    color.setFill()
    for (dx, dy) in [(0, 0), (1, 0), (0, 1), (1, 1)] {
        NSBezierPath(roundedRect: NSRect(x: x + CGFloat(dx) * (p + g), y: y + CGFloat(dy) * (p + g), width: p, height: p),
                     xRadius: size * 0.04, yRadius: size * 0.04).fill()
    }
}
grid(330, 270, 430, NSColor.white.withAlphaComponent(0.35))
grid(260, 340, 430, NSColor.white)
img.unlockFocus()
let set = out + "/AppIcon.iconset"
try? FileManager.default.createDirectory(atPath: set, withIntermediateDirectories: true)
for px in [16, 32, 64, 128, 256, 512, 1024] {
    let r = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: px, pixelsHigh: px, bitsPerSample: 8, samplesPerPixel: 4,
                             hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: r)
    img.draw(in: NSRect(x: 0, y: 0, width: px, height: px))
    NSGraphicsContext.restoreGraphicsState()
    let png = r.representation(using: .png, properties: [:])!
    for (name, want) in [("icon_\(px)x\(px).png", px), ("icon_\(px / 2)x\(px / 2)@2x.png", px)] where want == px {
        if name.contains("@2x") && px < 32 { continue }
        if !name.contains("@2x") && px > 512 { continue }
        try! png.write(to: URL(fileURLWithPath: set + "/" + name))
    }
}
