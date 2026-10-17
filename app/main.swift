// MacX — a Windows side for your Mac: two Wine engines, the Windows C: drive,
// and the "MacX" Desktop folder, which Windows programs see as drive W:.
import AppKit
import CoreServices
import SwiftUI
import UniformTypeIdentifiers

// MARK: - Models

struct Proc: Codable, Hashable { let pid: Int; let exe: String; let path: String; let engine: String }
struct RunningGame: Codable, Hashable { let name: String; let exe: String; let pid: Int }
struct RunningItem: Codable, Hashable { let id: String; let exe: String; let pid: Int; let engine: String }

struct Engine: Codable, Hashable, Identifiable {
    let id: String
    let name: String
    let short: String
    let available: Bool
    let ready: Bool
    let wDrive: Bool
    let cDrive: String
}

struct StatusInfo: Codable {
    let steamRunning: Bool
    let processes: [Proc]
    let runningGames: [RunningGame]
    let runningItems: [RunningItem]
    let freeBytes: Int64
    let totalBytes: Int64
    let hud: Bool
    let root: String
    let cDrive: String
    let drop: String
    let dropExists: Bool
    let engines: [Engine]
    let setupOK: Bool
}

struct DropItem: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let kind: String
    let path: String
    let winPath: String
    let baseDir: String
    let exes: [String]
    let mainExe: String?
    let bits: Int?
    let apis: [String]
    let api: String
    let engine: String
    let autoEngine: String
    let effectiveEngine: String
    let gfx: String
    let autoGfx: String
    let effectiveGfx: String
    let args: String
    let size: Int64
    let running: Bool
    let pids: [Int]
    let diskLetter: String?
    let log: String
}

struct WinProgram: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let folder: String
    let path: String
    let engine: String
    let engineName: String
}

struct Game: Codable, Identifiable, Hashable {
    let appid: String
    let name: String
    let installdir: String
    let path: String
    let size: Int64
    let flags: Int
    let state: String
    let manifest: String
    let exes: [String]
    let mainExe: String?
    let mode: String
    let launchOptions: String
    let dx12: Bool
    var id: String { appid }
}

struct StorageItem: Codable, Identifiable, Hashable {
    let id: String
    let group: String
    let name: String
    let path: String
    let size: Int64
    let removable: Bool
    let note: String
}

/// Something in a box: a file on its W: drive, or a game/program installed inside it.
struct BoxEntry: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let kind: String
    let path: String
    let winPath: String?
    let api: String
    let bits: Int?
    let choice: String
    let auto: String
    let effective: String
    let running: Bool
    let status: String?
    let pending: Bool?
    let playable: Bool?
    let source: String?
    let log: String
    let args: String?
    let kindSetting: String?
}
struct TaskResult: Codable, Hashable { let id: String; let state: String; let message: String }
struct BoxTask: Codable, Hashable {
    let label: String
    let done: Int
    let total: Int
    let finished: Bool
    let results: [TaskResult]?
}
struct WinBox: Codable, Identifiable, Hashable {
    var id: String { name }
    let name: String
    let path: String
    let running: Bool
    let files: [BoxEntry]
    let apps: [BoxEntry]
    let task: BoxTask?
    let pending: Int
    var busy: Bool { task.map { !$0.finished } ?? false }
    /// Everything that can be played: installed games first, then games sitting on W:.
    var games: [BoxEntry] { apps + files.filter { $0.playable == true } }
    var setupFiles: [BoxEntry] { files.filter { ["installer", "archive", "disk"].contains($0.kind) } }
    var otherFiles: [BoxEntry] { files.filter { $0.playable != true && !["installer", "archive", "disk"].contains($0.kind) } }
}
struct BoxesResp: Codable {
    let ok: Bool; let error: String?; let boxes: [WinBox]?; let root: String?; let canMigrate: Bool?; let canClone: Bool?
}

struct Check: Codable, Hashable { let name: String; let status: String }
struct PathItem: Codable, Hashable { let name: String; let path: String }

struct MsgResp: Codable { let ok: Bool; let error: String?; let message: String? }
struct PreCheck: Codable, Hashable { let name: String; let ok: Bool; let detail: String; let fix: String }
struct PreflightResp: Codable { let ok: Bool; let checks: [PreCheck]? }
struct InstallStatus: Codable { let step: String; let stepIndex: Int?; let steps: [String]?; let detail: String?
    let fraction: Double?; let done: Bool; let error: String? }
struct ItemsResp: Codable { let ok: Bool; let error: String?; let items: [DropItem]? }
struct ProgramsResp: Codable { let ok: Bool; let error: String?; let programs: [WinProgram]? }
struct GamesResp: Codable { let ok: Bool; let error: String?; let games: [Game]? }
struct StorageResp: Codable { let ok: Bool; let error: String?; let items: [StorageItem]?; let freeBytes: Int64?; let totalBytes: Int64? }
struct RepairResp: Codable { let ok: Bool; let error: String?; let checks: [Check]? }
struct PathsResp: Codable { let ok: Bool; let error: String?; let paths: [PathItem]? }

let dropPath = NSHomeDirectory() + "/Desktop/MacX"
let boxesPath = ProcessInfo.processInfo.environment["MACX_BOXES"] ?? NSHomeDirectory() + "/MacX Boxes"

// MARK: - Backend bridge

enum Backend {
    static var script: String {
        Bundle.main.path(forResource: "macxctl", ofType: "py") ?? "macxctl.py"
    }

    /// Commands that only read state: they get a time limit, so one blocked by the file system (for example
    /// macOS waiting for permission to read the Desktop folder) can never keep the app waiting forever.
    static let readOnly: Set<String> = ["status", "items", "programs", "games", "paths", "storage"]

    static func raw(_ args: [String]) async -> Data {
        let limit: Double? = readOnly.contains(args.first ?? "") || args.prefix(2) == ["box", "list"] ? 45 : nil
        return await withCheckedContinuation { cont in
            DispatchQueue.global(qos: .userInitiated).async {
                let p = Process()
                p.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
                p.arguments = [script] + args
                let pipe = Pipe()
                p.standardOutput = pipe
                p.standardError = FileHandle.nullDevice
                do { try p.run() } catch {
                    cont.resume(returning: Data("{\"ok\":false,\"error\":\"Couldn't start helper: \(error.localizedDescription)\"}".utf8))
                    return
                }
                if let limit {
                    DispatchQueue.global().asyncAfter(deadline: .now() + limit) { if p.isRunning { p.terminate() } }
                }
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                p.waitUntilExit()
                cont.resume(returning: data)
            }
        }
    }

    static func call<T: Decodable>(_ type: T.Type, _ args: [String]) async -> T? {
        let data = await raw(args)
        return try? JSONDecoder().decode(T.self, from: data)
    }
}

func fmtBytes(_ b: Int64) -> String {
    let f = ByteCountFormatter()
    f.countStyle = .file
    return f.string(fromByteCount: b)
}

func reveal(_ path: String) {
    let url = URL(fileURLWithPath: path)
    if FileManager.default.fileExists(atPath: path) {
        NSWorkspace.shared.activateFileViewerSelecting([url])
    } else {
        NSWorkspace.shared.open(url.deletingLastPathComponent())
    }
}

func engineShort(_ id: String) -> String {
    switch id {
    case "d3dmetal": return "D3DMetal"
    case "gptk77": return "GPTK 7.7"
    case "wine11": return "Wine 11"
    default: return "Auto"
    }
}

func gfxName(_ m: String) -> String {
    switch m {
    case "dxmt": return "DXMT"
    case "dxvk": return "DXVK"
    case "wine": return "Wine built-in"
    default: return "Auto"
    }
}

// MARK: - Folder watcher

final class FolderWatcher {
    private var stream: FSEventStreamRef?
    private let onChange: () -> Void
    fileprivate let ignore: (String) -> Bool

    /// ignore: paths whose changes don't matter (e.g. a box's own bookkeeping in .macx).
    init(path: String, ignore: @escaping (String) -> Bool = { _ in false }, onChange: @escaping () -> Void) {
        self.onChange = onChange
        self.ignore = ignore
        var ctx = FSEventStreamContext(version: 0, info: Unmanaged.passUnretained(self).toOpaque(),
                                       retain: nil, release: nil, copyDescription: nil)
        let cb: FSEventStreamCallback = { _, info, count, paths, _, _ in
            guard let info else { return }
            let w = Unmanaged<FolderWatcher>.fromOpaque(info).takeUnretainedValue()
            let list = paths.assumingMemoryBound(to: UnsafePointer<CChar>.self)
            for i in 0..<count where !w.ignore(String(cString: list[i])) {
                w.onChange()
                return
            }
        }
        guard let s = FSEventStreamCreate(nil, cb, &ctx, [path] as CFArray,
                                          FSEventStreamEventId(kFSEventStreamEventIdSinceNow), 1.0,
                                          FSEventStreamCreateFlags(kFSEventStreamCreateFlagFileEvents))
        else { return }
        stream = s
        FSEventStreamSetDispatchQueue(s, DispatchQueue.main)
        FSEventStreamStart(s)
    }

    deinit {
        if let s = stream { FSEventStreamStop(s); FSEventStreamInvalidate(s); FSEventStreamRelease(s) }
    }
}

// MARK: - App model

@MainActor
final class AppModel: ObservableObject {
    static let shared = AppModel()

    @Published var status: StatusInfo?
    @Published var items: [DropItem] = []
    @Published var programs: [WinProgram] = []
    @Published var games: [Game] = []
    @Published var storage: [StorageItem] = []
    @Published var storageLoading = false
    @Published var checks: [Check] = []
    @Published var paths: [PathItem] = []
    @Published var busy: String?
    @Published var banner: (text: String, isError: Bool)?
    @Published var boxes: [WinBox] = []
    @Published var canMigrate = false
    @Published var canClone = false
    private var timer: Timer?
    private var watcher: FolderWatcher?
    private var boxWatcher: FolderWatcher?
    private var boxesPending = false
    private var itemsPending = false

    init() {
        Task { await start() }
        timer = Timer.scheduledTimer(withTimeInterval: 4, repeats: true) { [weak self] _ in
            Task { @MainActor in
                await self?.refreshStatus()
                // keep boxes live while something runs or is being set up in one
                if self?.boxes.contains(where: { $0.running || $0.busy }) == true { await self?.refreshBoxes() }
            }
        }
    }

    func start() async {
        _ = await Backend.call(MsgResp.self, ["setup"])
        try? FileManager.default.createDirectory(atPath: boxesPath, withIntermediateDirectories: true)
        await refreshStatus()
        await refreshBoxes()   // boxes first: they don't depend on the Desktop folder (which macOS may ask about)
        await refreshAll()
        // Watching folders talks to the file system (and, for an iCloud-synced Desktop, to iCloud), which can be
        // slow; it happens off the main thread so the window never freezes waiting for it.
        let dropW = await Task.detached { FolderWatcher(path: dropPath) {
            Task { @MainActor in AppModel.shared.scheduleItemsRefresh() }
        } }.value
        // Boxes added, changed or moved to the Trash in Finder show up here without pressing anything.
        let boxW = await Task.detached { FolderWatcher(path: boxesPath, ignore: { $0.contains("/.macx/") || $0.hasSuffix("/.macx") }) {
            Task { @MainActor in AppModel.shared.scheduleBoxesRefresh() }
        } }.value
        watcher = dropW
        boxWatcher = boxW
        let needsIcon = await Task.detached {
            FileManager.default.fileExists(atPath: dropPath) && !FileManager.default.fileExists(atPath: dropPath + "/Icon\r")
        }.value
        if needsIcon { decorateFolder() }
    }

    func refreshAll() async {
        await refreshStatus()
        await refreshItems()
        await refreshPrograms()
        await refreshGames()
        if let p = await Backend.call(PathsResp.self, ["paths"]) { paths = p.paths ?? [] }
    }

    func refreshStatus() async {
        if let s = await Backend.call(StatusInfo.self, ["status"]) {
            let runningChanged = s.runningItems.map(\.id) != (status?.runningItems.map(\.id) ?? [])
            status = s
            if runningChanged { await refreshItems() }
        }
    }

    func scheduleItemsRefresh() {
        if itemsPending { return }
        itemsPending = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [weak self] in
            Task { @MainActor in
                self?.itemsPending = false
                await self?.refreshItems()
            }
        }
    }

    func scheduleBoxesRefresh() {
        if boxesPending { return }
        boxesPending = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { [weak self] in
            Task { @MainActor in
                self?.boxesPending = false
                await self?.refreshBoxes()
            }
        }
    }

    func refreshBoxes() async {
        if let r = await Backend.call(BoxesResp.self, ["box", "list"]), let list = r.boxes {
            boxes = list
            canMigrate = r.canMigrate ?? false
            canClone = r.canClone ?? false
        }
    }

    /// Adds any number of files/folders to a box (copied in; instant on the same disk) and sets them up.
    func addToBox(_ box: String, _ urls: [URL]) async {
        guard !urls.isEmpty else { return }
        await boxAct(urls.count == 1 ? "Adding \(urls[0].lastPathComponent)…" : "Adding \(urls.count) items…",
                     ["add", box, "--setup"] + urls.map(\.path))
    }

    func boxAct(_ label: String, _ args: [String]) async {
        await act(label, ["box"] + args)
        await refreshBoxes()
    }

    func refreshItems() async {
        if let r = await Backend.call(ItemsResp.self, ["items"]), let list = r.items { items = list }
    }

    func refreshPrograms() async {
        if let r = await Backend.call(ProgramsResp.self, ["programs"]), let list = r.programs { programs = list }
    }

    func refreshGames() async {
        if let g = await Backend.call(GamesResp.self, ["games"]), let list = g.games { games = list }
    }

    func refreshStorage() async {
        storageLoading = true
        if let s = await Backend.call(StorageResp.self, ["storage"]) { storage = s.items ?? [] }
        storageLoading = false
    }

    func act(_ label: String, _ args: [String], thenGames: Bool = false, thenItems: Bool = false) async {
        busy = label
        let r = await Backend.call(MsgResp.self, args)
        busy = nil
        if let r {
            show(r.ok ? (r.message ?? "Done.") : (r.error ?? "Something went wrong."), error: !r.ok)
        } else {
            show("No response from the helper.", error: true)
        }
        await refreshStatus()
        if thenGames { await refreshGames() }
        if thenItems { await refreshItems(); await refreshPrograms() }
    }

    func setItem(_ id: String, _ field: String, _ value: String) async {
        _ = await Backend.call(MsgResp.self, ["item-set", id, field, value])
        await refreshItems()
    }

    func repair() async {
        busy = "Checking setup…"
        let r = await Backend.call(RepairResp.self, ["repair"])
        busy = nil
        checks = r?.checks ?? []
        let problems = checks.filter { $0.status == "problem" }.count
        let fixed = checks.filter { $0.status == "fixed" }.count
        show(problems > 0 ? "\(problems) problem(s) need attention." :
                (fixed > 0 ? "Fixed \(fixed) item(s). Everything looks good now." : "Everything looks good."),
             error: problems > 0)
    }

    /// Copies files dragged onto the app into the MacX folder.
    func addToFolder(_ urls: [URL]) {
        let urls = urls.filter { !$0.path.hasPrefix(dropPath + "/") }
        guard !urls.isEmpty else { return }
        busy = urls.count == 1 ? "Copying \(urls[0].lastPathComponent)…" : "Copying \(urls.count) items…"
        DispatchQueue.global(qos: .userInitiated).async {
            var failed: String?
            for url in urls {
                var dest = URL(fileURLWithPath: dropPath).appendingPathComponent(url.lastPathComponent)
                var n = 2
                while FileManager.default.fileExists(atPath: dest.path) {
                    let ext = url.pathExtension
                    let base = url.deletingPathExtension().lastPathComponent
                    dest = URL(fileURLWithPath: dropPath).appendingPathComponent(ext.isEmpty ? "\(base) (\(n))" : "\(base) (\(n)).\(ext)")
                    n += 1
                }
                do { try FileManager.default.copyItem(at: url, to: dest) } catch { failed = error.localizedDescription }
            }
            DispatchQueue.main.async {
                self.busy = nil
                if let failed { self.show("Couldn't copy: \(failed)", error: true) } else { self.show("Added to MacX (drive W:).") }
                Task { await self.refreshItems() }
            }
        }
    }

    func openFromFinder(_ urls: [URL]) {
        for url in urls {
            Task { await act("Starting \(url.lastPathComponent)…", ["open", url.path], thenItems: true) }
        }
    }

    /// Gives the Desktop folder the app's icon, so it's obvious it belongs to MacX.
    func decorateFolder() {
        guard FileManager.default.fileExists(atPath: dropPath),
              !FileManager.default.fileExists(atPath: dropPath + "/Icon\r") else { return }
        NSWorkspace.shared.setIcon(folderIcon(), forFile: dropPath, options: [])
        // Wine reads DOS attributes from this xattr: mark the icon file hidden so Windows doesn't list it.
        _ = setxattr(dropPath + "/Icon\r", "user.DOSATTRIB", "0x2", 3, 0, 0)
    }

    func show(_ text: String, error: Bool = false) {
        banner = (text, error)
        let current = text
        DispatchQueue.main.asyncAfter(deadline: .now() + 7) { [weak self] in
            if self?.banner?.text == current { self?.banner = nil }
        }
    }
}

/// A folder with the MacX badge, drawn at runtime.
func folderIcon() -> NSImage {
    let base = NSWorkspace.shared.icon(for: .folder)
    base.size = NSSize(width: 512, height: 512)
    let img = NSImage(size: NSSize(width: 512, height: 512))
    img.lockFocus()
    base.draw(in: NSRect(x: 0, y: 0, width: 512, height: 512))
    let badge = NSApp.applicationIconImage ?? NSImage()
    badge.draw(in: NSRect(x: 156, y: 96, width: 200, height: 200))
    img.unlockFocus()
    return img
}

// MARK: - App

final class AppDelegate: NSObject, NSApplicationDelegate {
    func application(_ application: NSApplication, open urls: [URL]) {
        Task { @MainActor in AppModel.shared.openFromFinder(urls) }
    }
}

@main
struct MacXApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject private var model = AppModel.shared
    var body: some Scene {
        WindowGroup("MacX") {
            ContentView().environmentObject(model).frame(minWidth: 1220, minHeight: 680)
        }
        .windowResizability(.contentMinSize)
    }
}

enum NavSection: String, CaseIterable, Identifiable {
    case pc = "This PC", folder = "MacX Drive", boxes = "Boxes", programs = "Programs", steam = "Steam", storage = "Storage",
         tools = "Tools", help = "Help"
    var id: String { rawValue }
    var icon: String {
        switch self {
        case .pc: return "desktopcomputer"
        case .folder: return "folder.fill"
        case .boxes: return "shippingbox"
        case .programs: return "square.grid.2x2"
        case .steam: return "gamecontroller"
        case .storage: return "internaldrive"
        case .tools: return "wrench.and.screwdriver"
        case .help: return "questionmark.circle"
        }
    }
}

struct ContentView: View {
    @EnvironmentObject var model: AppModel
    @State private var section: NavSection? = .boxes

    var body: some View {
        if let st = model.status, !st.setupOK {
            SetupView().frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            mainView
        }
    }

    var mainView: some View {
        NavigationSplitView {
            List(NavSection.allCases, selection: $section) { s in
                Label(s.rawValue, systemImage: s.icon).tag(s)
            }
            .navigationSplitViewColumnWidth(min: 170, ideal: 190)
            .safeAreaInset(edge: .bottom) { StatusPills().padding(10) }
        } detail: {
            ZStack(alignment: .bottom) {
                Group {
                    switch section ?? .folder {
                    case .pc: ThisPCView()
                    case .folder: FolderView()
                    case .boxes: BoxesView()
                    case .programs: ProgramsView()
                    case .steam: GamesView()
                    case .storage: StorageView()
                    case .tools: ToolsView()
                    case .help: HelpView()
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                BannerView()
            }
        }
    }
}

struct StatusPills: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            pill(model.status?.dropExists ?? false, on: "W: drive connected", off: "W: drive missing")
            pill(model.status?.steamRunning ?? false, on: "Steam running", off: "Steam stopped")
            let n = model.status?.runningItems.count ?? 0
            if n > 0 { pill(true, on: "\(n) running from W:", off: "") }
        }
    }

    func pill(_ on: Bool, on onText: String, off offText: String) -> some View {
        HStack(spacing: 6) {
            Circle().fill(on ? Color.green : Color.secondary.opacity(0.5)).frame(width: 8, height: 8)
            Text(on ? onText : offText).font(.caption).foregroundStyle(.secondary)
            Spacer()
        }
    }
}

struct BannerView: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        VStack(spacing: 8) {
            if let busy = model.busy {
                HStack(spacing: 8) { ProgressView().controlSize(.small); Text(busy) }
                    .padding(.horizontal, 14).padding(.vertical, 9)
                    .background(.regularMaterial, in: Capsule())
            }
            if let b = model.banner {
                HStack(spacing: 8) {
                    Image(systemName: b.isError ? "exclamationmark.triangle.fill" : "checkmark.circle.fill")
                        .foregroundStyle(b.isError ? .orange : .green)
                    Text(b.text).fixedSize(horizontal: false, vertical: true)
                    Button { model.banner = nil } label: { Image(systemName: "xmark") }.buttonStyle(.plain)
                }
                .padding(.horizontal, 14).padding(.vertical, 10)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10))
                .frame(maxWidth: 560)
            }
        }
        .padding(.bottom, 16)
        .animation(.easeInOut(duration: 0.2), value: model.busy)
    }
}

// MARK: - MacX folder (W:)

struct KindInfo { let label: String; let icon: String; let group: String }

func kindInfo(_ k: String) -> KindInfo {
    switch k {
    case "program": return KindInfo(label: "Program", icon: "macwindow", group: "Programs & games")
    case "folder": return KindInfo(label: "Program folder", icon: "folder.fill", group: "Programs & games")
    case "installer": return KindInfo(label: "Installer", icon: "shippingbox", group: "Installers")
    case "disk": return KindInfo(label: "Disc image", icon: "opticaldisc", group: "Disc images")
    case "archive": return KindInfo(label: "Archive", icon: "doc.zipper", group: "Archives")
    case "shortcut": return KindInfo(label: "Shortcut", icon: "arrowshape.turn.up.right", group: "Shortcuts & scripts")
    case "script": return KindInfo(label: "Batch script", icon: "terminal", group: "Shortcuts & scripts")
    case "registry": return KindInfo(label: "Registry file", icon: "list.bullet.rectangle", group: "Shortcuts & scripts")
    case "files": return KindInfo(label: "Folder", icon: "folder", group: "Other files")
    default: return KindInfo(label: "File", icon: "doc", group: "Other files")
    }
}

let kindGroups = ["Programs & games", "Installers", "Disc images", "Archives", "Shortcuts & scripts", "Other files"]

struct FolderView: View {
    @EnvironmentObject var model: AppModel
    @State private var selected: String?
    @State private var dropTargeted = false

    var body: some View {
        HSplitView {
            VStack(alignment: .leading, spacing: 0) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("MacX").font(.title2.weight(.semibold))
                    Text("Desktop folder · drive W: in Windows").font(.caption).foregroundStyle(.secondary)
                }.padding(.horizontal, 14).padding(.top, 14).padding(.bottom, 8)
                List(selection: $selected) {
                    let groups = Dictionary(grouping: model.items, by: { kindInfo($0.kind).group })
                    ForEach(kindGroups, id: \.self) { g in
                        if let list = groups[g], !list.isEmpty {
                            Section(g) {
                                ForEach(list) { it in ItemRow(item: it).tag(it.id) }
                            }
                        }
                    }
                }
                .overlay {
                    if model.items.isEmpty {
                        VStack(spacing: 10) {
                            Image(systemName: "tray.and.arrow.down").font(.system(size: 36)).foregroundStyle(.secondary)
                            Text("Drop Windows games, programs, installers, .iso discs or .zip files here — or into the MacX folder on your Desktop.")
                                .multilineTextAlignment(.center).foregroundStyle(.secondary).padding(.horizontal, 20)
                        }
                    }
                }
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.accentColor, lineWidth: dropTargeted ? 3 : 0).padding(4))
                .onDrop(of: [.fileURL], isTargeted: $dropTargeted) { providers in
                    loadURLs(providers) { model.addToFolder($0) }
                    return true
                }
                Divider()
                HStack {
                    Button { pickFiles() } label: { Label("Add…", systemImage: "plus") }
                    Button { reveal(dropPath) } label: { Label("Show in Finder", systemImage: "folder") }
                    Spacer()
                    Button { Task { await model.act("Opening W:…", ["tool", "explorer"]) } } label: {
                        Image(systemName: "macwindow")
                    }.help("Open W: in the Windows file manager")
                }.padding(10)
            }
            .frame(minWidth: 280, idealWidth: 320, maxWidth: 400)

            Group {
                if let it = model.items.first(where: { $0.id == selected }) {
                    ItemDetail(item: it).id(it.id)
                } else {
                    VStack(spacing: 12) {
                        Image(systemName: "externaldrive.fill.badge.checkmark").font(.system(size: 44)).foregroundStyle(.secondary)
                        Text(model.items.isEmpty ? "Your W: drive is empty." : "Select something on the W: drive.")
                            .font(.title3).foregroundStyle(.secondary)
                        Text("Anything you put in the MacX folder appears here, the way it would on a Windows PC.")
                            .foregroundStyle(.secondary)
                    }.frame(maxWidth: .infinity, maxHeight: .infinity).padding()
                }
            }
            .frame(minWidth: 500, maxWidth: .infinity, maxHeight: .infinity)
        }
        .onAppear {
            Task { await model.refreshItems() }
            if selected == nil { selected = model.items.first?.id }
        }
        .onChange(of: model.items) { _, items in
            if selected == nil || !items.contains(where: { $0.id == selected }) { selected = items.first?.id }
        }
    }

    func pickFiles() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = true
        panel.prompt = "Add to W:"
        panel.message = "Choose Windows games, programs, installers, disc images or archives. They're copied into the MacX folder."
        if panel.runModal() == .OK { model.addToFolder(panel.urls) }
    }
}

func loadURLs(_ providers: [NSItemProvider], _ done: @escaping ([URL]) -> Void) {
    var urls: [URL] = []
    let group = DispatchGroup()
    let lock = NSLock()
    for p in providers {
        group.enter()
        _ = p.loadObject(ofClass: URL.self) { url, _ in
            if let url { lock.lock(); urls.append(url); lock.unlock() }
            group.leave()
        }
    }
    group.notify(queue: .main) { done(urls) }
}

// MARK: - Boxes

/// One folder in ~/MacX Boxes = one sealed-off Windows PC. The Windows side (registry, C:, saves) lives in the
/// folder's hidden .macx, so deleting the folder in Finder deletes everything.
struct BoxesView: View {
    @EnvironmentObject var model: AppModel
    @State private var selected: String?
    @State private var confirmDelete: WinBox?
    @State private var confirmMigrate = false
    @State private var confirmClone = false
    @State private var dropTarget: String?

    var body: some View {
        HSplitView {
            VStack(alignment: .leading, spacing: 0) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Boxes").font(.title2.weight(.semibold))
                    Text("Each folder is its own Windows PC").font(.caption).foregroundStyle(.secondary)
                }.padding(.horizontal, 14).padding(.top, 14).padding(.bottom, 8)
                List(model.boxes, selection: $selected) { b in
                    HStack(spacing: 10) {
                        Image(systemName: "shippingbox.fill").frame(width: 22).foregroundStyle(Color.accentColor)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(b.name).font(.headline).lineLimit(1)
                            HStack(spacing: 6) {
                                Text(b.games.count == 1 ? "1 game" : "\(b.games.count) games")
                                if b.busy { Text("Setting up…").foregroundStyle(.orange) }
                                else if b.running { Text("Running").foregroundStyle(.green) }
                                else if b.pending > 0 { Text("\(b.pending) to set up").foregroundStyle(.orange) }
                            }.font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .padding(.vertical, 3).tag(b.name)
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.accentColor, lineWidth: dropTarget == b.name ? 2 : 0))
                    .onDrop(of: [.fileURL], isTargeted: Binding(get: { dropTarget == b.name },
                                                                set: { dropTarget = $0 ? b.name : nil })) { providers in
                        loadURLs(providers) { urls in Task { await model.addToBox(b.name, urls) } }
                        return true
                    }
                }
                .overlay {
                    if model.boxes.isEmpty {
                        Text("No boxes yet. A box is a folder that acts as a separate Windows PC: drop games, installers, archives or disc images into it, and what runs in it can't see the rest of your Mac.")
                            .multilineTextAlignment(.center).foregroundStyle(.secondary).padding(.horizontal, 20)
                    }
                }
                if model.canClone {
                    Button { confirmClone = true } label: {
                        Label("Copy my Steam setup into a box", systemImage: "plus.square.on.square")
                    }.buttonStyle(.link).padding(.horizontal, 14).padding(.top, 6)
                }
                if model.canMigrate {
                    Button { confirmMigrate = true } label: {
                        Label("Move my existing setup into a box", systemImage: "arrow.right.square")
                    }.buttonStyle(.link).padding(.horizontal, 14).padding(.vertical, 6)
                }
                Divider()
                HStack {
                    Button { Task { await model.boxAct("Creating a box…", ["new"]) } } label: {
                        Label("New Box", systemImage: "plus")
                    }
                    Button { reveal(boxesPath) } label: { Label("Show in Finder", systemImage: "folder") }
                    Spacer()
                }.padding(10)
            }
            .frame(minWidth: 230, idealWidth: 260, maxWidth: 340)

            Group {
                if let b = model.boxes.first(where: { $0.name == selected }) {
                    BoxDetail(box: b, onDelete: { confirmDelete = b })
                } else {
                    VStack(spacing: 12) {
                        Image(systemName: "shippingbox").font(.system(size: 44)).foregroundStyle(.secondary)
                        Text("Select a box, or make a new one.").font(.title3).foregroundStyle(.secondary)
                    }.frame(maxWidth: .infinity, maxHeight: .infinity).padding()
                }
            }
            .frame(minWidth: 560, maxWidth: .infinity, maxHeight: .infinity)
        }
        .onAppear {
            Task { await model.refreshBoxes() }
            if selected == nil { selected = model.boxes.first?.name }
        }
        .onChange(of: model.boxes) { _, boxes in
            if selected == nil || !boxes.contains(where: { $0.name == selected }) { selected = boxes.first?.name }
        }
        .confirmationDialog("Move “\(confirmDelete?.name ?? "")” to the Trash?", isPresented: Binding(
            get: { confirmDelete != nil }, set: { if !$0 { confirmDelete = nil } })) {
            Button("Move to Trash", role: .destructive) {
                if let b = confirmDelete { Task { await model.boxAct("Deleting \(b.name)…", ["delete", b.name]) } }
            }
        } message: {
            Text("Everything in it — games, saves and its Windows settings — goes to the Trash. Programs running in it are stopped.")
        }
        .confirmationDialog("Copy your Steam setup into a new box?", isPresented: $confirmClone) {
            Button("Copy into a box") { Task { await model.boxAct("Copying your setup…", ["clone-main"]) } }
        } message: {
            Text("Makes a box that starts with your current C: drive — Steam, installed games, saves. It's a copy-on-write clone: instant, and it takes no extra disk space until something changes. Your existing setup is not touched. Quit Steam first.")
        }
        .confirmationDialog("Move your existing setup into a box called “Main”?", isPresented: $confirmMigrate) {
            Button("Move into “Main”") { Task { await model.boxAct("Moving your setup…", ["migrate"]) } }
        } message: {
            Text("Your Windows drive C: (including Steam and installed games) and the MacX folder are moved — not copied — into MacX Boxes/Main. The Steam page keeps working. The box no longer has a Z: drive, so Windows programs in it can't see the rest of your Mac. Quit Steam first.")
        }
    }
}

func choiceName(_ c: String) -> String {
    switch c {
    case "d3dmetal": return "D3DMetal"
    case "dxmt": return "DXMT"
    case "wine": return "Wine"
    default: return "Auto"
    }
}

struct BoxDetail: View {
    @EnvironmentObject var model: AppModel
    let box: WinBox
    let onDelete: () -> Void
    @State private var dropTargeted = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            if let t = box.task, !t.finished {
                HStack(spacing: 10) {
                    ProgressView(value: Double(t.done), total: Double(max(t.total, 1))).frame(width: 140)
                    Text("\(t.label)  (\(min(t.done + 1, t.total)) of \(t.total))").font(.callout)
                    Spacer()
                }.padding(.horizontal, 16).padding(.vertical, 8).background(Color.orange.opacity(0.12))
            }
            Divider()
            if box.files.isEmpty && box.apps.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "tray.and.arrow.down").font(.system(size: 40)).foregroundStyle(.secondary)
                    Text("Drop anything Windows here — as many as you like").font(.title3)
                    Text("Game folders, single .exe programs, installers (setup.exe, also with data-1.bin, data-2.bin… beside it), .msi, .zip / .7z / .rar archives and .iso disc images. MacX unpacks, inserts and installs them one after another, then lists the games ready to play on Metal.")
                        .multilineTextAlignment(.center).foregroundStyle(.secondary).frame(maxWidth: 460)
                    Button { pickFiles() } label: { Label("Add Files…", systemImage: "plus") }.controlSize(.large)
                }.frame(maxWidth: .infinity, maxHeight: .infinity).padding()
            } else {
                List {
                    if !box.games.isEmpty {
                        Section("Games & programs") {
                            ForEach(box.games) { it in GameRow(box: box.name, item: it) }
                        }
                    }
                    if !box.setupFiles.isEmpty {
                        Section("Installers, archives & discs") {
                            ForEach(box.setupFiles) { it in SetupRow(box: box.name, item: it, busy: box.busy) }
                        }
                    }
                    if !box.otherFiles.isEmpty {
                        Section("Other files on W:") {
                            ForEach(box.otherFiles) { it in
                                HStack {
                                    Image(systemName: "doc").frame(width: 22).foregroundStyle(.secondary)
                                    Text(it.name)
                                    Spacer()
                                    if ["shortcut", "script", "file"].contains(it.kind) {
                                        Button("Open") { Task { await model.boxAct("Opening \(it.name)…", ["play", box.name, it.id]) } }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.accentColor, lineWidth: dropTargeted ? 3 : 0).padding(4))
        .onDrop(of: [.fileURL], isTargeted: $dropTargeted) { providers in
            loadURLs(providers) { urls in Task { await model.addToBox(box.name, urls) } }
            return true
        }
    }

    var header: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 4) {
                Text(box.name).font(.title2.weight(.semibold))
                Text(box.path).font(.caption).foregroundStyle(.secondary).textSelection(.enabled).lineLimit(1)
            }
            Spacer()
            Button { pickFiles() } label: { Label("Add Files…", systemImage: "plus") }
            if box.pending > 0 && !box.busy {
                Button { Task { await model.boxAct("Setting up…", ["setup", box.name]) } } label: {
                    Label("Set Up All (\(box.pending))", systemImage: "wand.and.stars")
                }.buttonStyle(.borderedProminent)
            }
            if box.running || box.busy {
                Button { Task { await model.boxAct("Stopping…", ["stop", box.name]) } } label: {
                    Label("Stop All", systemImage: "stop.fill")
                }
            }
            Menu {
                Button("Show in Finder") { reveal(box.path) }
                Button("Show Logs") { NSWorkspace.shared.open(URL(fileURLWithPath: box.path + "/.macx/logs")) }
                Divider()
                Button("Delete Box…", role: .destructive, action: onDelete)
            } label: { Image(systemName: "ellipsis.circle") }.menuStyle(.borderlessButton).frame(width: 34)
        }.padding(16)
    }

    func pickFiles() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = true
        panel.allowsMultipleSelection = true
        panel.prompt = "Add to \(box.name)"
        panel.message = "Choose any number of Windows games, programs, installers (or installer folders), archives or disc images."
        if panel.runModal() == .OK { Task { await model.addToBox(box.name, panel.urls) } }
    }
}

struct GameRow: View {
    @EnvironmentObject var model: AppModel
    let box: String
    let item: BoxEntry

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: item.kind == "steam" || item.kind == "steamgame" ? "gamecontroller.fill" : "app.dashed")
                .frame(width: 22).foregroundStyle(Color.accentColor)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(item.name).font(.headline).lineLimit(1)
                    if item.running { Text("Running").font(.caption).foregroundStyle(.green) }
                }
                Text(subtitle).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer()
            if item.kind != "steam" && item.kind != "steamgame" {
                Picker("", selection: Binding(
                    get: { item.choice },
                    set: { v in Task { await model.boxAct("Saving…", ["set", box, item.id, "engine", v]) } })) {
                    Text("Auto (\(choiceName(item.auto)))").tag("auto")
                    Text("D3DMetal").tag("d3dmetal")
                    Text("DXMT").tag("dxmt")
                    Text("Wine").tag("wine")
                }.frame(width: 150).labelsHidden()
                    .help("How the graphics reach Metal. D3DMetal: Apple's, for 64-bit DirectX 10–12. DXMT: DirectX 10/11, also 32-bit. Wine: DirectX 9 and older (OpenGL), Vulkan.")
            }
            if item.running {
                Button { Task { await model.boxAct("Closing \(item.name)…", ["stop", box, item.id]) } } label: {
                    Label("Stop", systemImage: "stop.fill")
                }
            } else {
                Button { Task { await model.boxAct("Starting \(item.name)…", ["play", box, item.id]) } } label: {
                    Label("Play", systemImage: "play.fill")
                }.buttonStyle(.borderedProminent)
            }
            if item.source == nil {   // on W:, so MacX guessed what it is
                Menu {
                    Button("Treat as an Installer") {
                        Task { await model.boxAct("Saving…", ["set", box, item.id, "kind", "installer"]) }
                    }
                    Button("Show Log") { NSWorkspace.shared.open(URL(fileURLWithPath: item.log)) }
                        .disabled(!FileManager.default.fileExists(atPath: item.log))
                } label: { Image(systemName: "ellipsis.circle") }
                    .menuStyle(.borderlessButton).frame(width: 30).help("More")
            }
        }.padding(.vertical, 4)
    }

    var subtitle: String {
        var parts: [String] = []
        if item.kind == "steamgame" { parts.append("Steam game") }
        else if item.kind == "steam" { parts.append("Steam") }
        else {
            if item.api != "Unknown" { parts.append(item.api) }
            if let b = item.bits { parts.append("\(b)-bit") }
            parts.append("→ " + choiceName(item.effective))
        }
        if let w = item.winPath { parts.append(w) }
        return parts.joined(separator: " · ")
    }
}

struct SetupRow: View {
    @EnvironmentObject var model: AppModel
    let box: String
    let item: BoxEntry
    let busy: Bool
    @State private var showOptions = false
    @State private var options = ""

    var icon: String {
        switch item.kind {
        case "archive": return "doc.zipper"
        case "disk": return "opticaldisc"
        default: return "shippingbox.and.arrow.backward"
        }
    }

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: icon).frame(width: 22).foregroundStyle(Color.accentColor)
            VStack(alignment: .leading, spacing: 2) {
                Text(item.name).font(.headline).lineLimit(1)
                Text(item.status ?? "").font(.caption)
                    .foregroundStyle(item.pending == true ? Color.orange : (item.status ?? "").contains("error") ? Color.red : Color.secondary)
            }
            Spacer()
            if item.kind == "disk", (item.status ?? "").contains("in drive") {
                Button("Eject") { Task { await model.boxAct("Ejecting…", ["eject", box, item.id]) } }
            }
            Button("Log") { NSWorkspace.shared.open(URL(fileURLWithPath: item.log)) }
                .disabled(!FileManager.default.fileExists(atPath: item.log))
            Button(action: { Task { await model.boxAct("Setting up \(item.name)…", ["setup", box, item.id]) } }) {
                Text(actionLabel)
            }.disabled(busy)
            if item.kind == "installer" {
                Menu {
                    Button("Install Options…") { options = item.args ?? ""; showOptions = true }
                    Button("Treat as a Program") {
                        Task { await model.boxAct("Saving…", ["set", box, item.id, "kind", "program"]) }
                    }
                } label: { Image(systemName: "ellipsis.circle") }
                    .menuStyle(.borderlessButton).frame(width: 30).help("More")
                    .popover(isPresented: $showOptions) {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Options passed to the installer").font(.headline)
                            Text("Most installers need none: you click through their window. To install without clicking, use /S for NSIS installers, /VERYSILENT for Inno Setup ones (most repacks), /quiet for Microsoft ones.")
                                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                            TextField("e.g. /S", text: $options).textFieldStyle(.roundedBorder)
                            HStack {
                                Spacer()
                                Button("Cancel") { showOptions = false }
                                Button("Save") {
                                    showOptions = false
                                    Task { await model.boxAct("Saving…", ["set", box, item.id, "args", options]) }
                                }.keyboardShortcut(.defaultAction)
                            }
                        }.padding(14).frame(width: 340)
                    }
            }
        }.padding(.vertical, 4)
    }

    var actionLabel: String {
        let again = item.pending != true
        switch item.kind {
        case "archive": return again ? "Unpack Again" : "Unpack"
        case "disk": return again ? "Run Setup Again" : "Insert & Install"
        default: return again ? "Install Again" : "Install"
        }
    }
}

struct ItemRow: View {
    let item: DropItem
    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: kindInfo(item.kind).icon).frame(width: 22).foregroundStyle(Color.accentColor)
            VStack(alignment: .leading, spacing: 2) {
                Text(item.name).font(.headline).lineLimit(1)
                HStack(spacing: 6) {
                    Text(kindInfo(item.kind).label)
                    if item.kind == "program" || item.kind == "folder" {
                        Badge(text: engineShort(item.effectiveEngine))
                        if item.api != "Unknown" { Text(item.api) }
                    }
                    if let d = item.diskLetter { Badge(text: "in \(d)") }
                    if item.running { Text("Running").foregroundStyle(.green) }
                }.font(.caption).foregroundStyle(.secondary)
            }
        }.padding(.vertical, 3)
    }
}

struct Badge: View {
    let text: String
    var body: some View {
        Text(text).padding(.horizontal, 6).padding(.vertical, 1)
            .background(Color.accentColor.opacity(0.15), in: Capsule())
    }
}

struct ItemDetail: View {
    @EnvironmentObject var model: AppModel
    let item: DropItem
    @State private var args = ""
    @State private var confirmTrash = false
    @State private var confirmReg = false

    var playable: Bool { item.kind == "program" || item.kind == "folder" }
    var usesEngine: Bool { playable || item.kind == "installer" || item.kind == "disk" || item.kind == "registry" }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack(alignment: .top, spacing: 14) {
                    Image(systemName: kindInfo(item.kind).icon).font(.system(size: 34)).foregroundStyle(Color.accentColor)
                        .frame(width: 48)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(item.name).font(.largeTitle.weight(.semibold)).lineLimit(2)
                        Text(subtitle).foregroundStyle(.secondary).textSelection(.enabled)
                    }
                }
                actions

                if usesEngine {
                    Card(title: "Engine", systemImage: "cpu") {
                        Picker("", selection: Binding(get: { item.engine },
                                                      set: { v in Task { await model.setItem(item.id, "engine", v) } })) {
                            Text("Auto (\(engineShort(item.autoEngine)))").tag("auto")
                            Text("Wine 11").tag("wine11")
                            Text("D3DMetal").tag("d3dmetal")
                        }.pickerStyle(.segmented).labelsHidden().disabled(item.running)
                        Text(engineHelp).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                        if item.kind == "installer" {
                            Label("Installers put the program on that engine's C: drive. Afterwards it's listed under Programs.",
                                  systemImage: "info.circle").font(.callout).foregroundStyle(.secondary)
                        }
                    }
                }

                if playable && item.effectiveEngine == "wine11" {
                    Card(title: "Graphics (DirectX translation)", systemImage: "square.3.layers.3d") {
                        Picker("", selection: Binding(get: { item.gfx },
                                                      set: { v in Task { await model.setItem(item.id, "gfx", v) } })) {
                            Text("Auto (\(gfxName(item.autoGfx)))").tag("auto")
                            Text("DXMT → Metal").tag("dxmt")
                            Text("DXVK → Vulkan → Metal").tag("dxvk")
                            Text("Wine built-in").tag("wine")
                        }.pickerStyle(.segmented).labelsHidden().disabled(item.running)
                        Text(gfxHelp(item.effectiveGfx)).font(.callout).foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                        if item.apis.contains("dx12") {
                            Label("This program uses DirectX 12. Only the D3DMetal engine translates DirectX 12 well.",
                                  systemImage: "exclamationmark.triangle").font(.callout).foregroundStyle(.orange)
                        }
                    }
                }

                if (playable || item.kind == "installer") && item.exes.count > 1 {
                    Card(title: "Main program", systemImage: "app") {
                        Picker("Program to start", selection: Binding(get: { item.mainExe ?? "" },
                                                                      set: { v in Task { await model.setItem(item.id, "exe", v) } })) {
                            ForEach(item.exes, id: \.self) { Text($0).tag($0) }
                        }
                        Text("Picked automatically (the biggest .exe that isn't a setup, updater or crash reporter). Change it if the game starts through a different program.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }

                if playable {
                    Card(title: "Launch options", systemImage: "terminal") {
                        TextField("e.g. -windowed -skipintro", text: $args).textFieldStyle(.roundedBorder)
                            .font(.system(.body, design: .monospaced))
                        HStack {
                            Text("Passed to the program, like a Windows shortcut's Target field.")
                                .font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            Button("Save") { Task { await model.setItem(item.id, "args", args); model.show("Launch options saved.") } }
                                .disabled(args == item.args)
                        }
                    }
                }

                Card(title: "Details", systemImage: "info.circle") {
                    InfoRow(label: "On Windows", value: item.winPath + (item.mainExe.map { item.kind == "folder" || item.kind == "installer" ? "\\" + $0.replacingOccurrences(of: "/", with: "\\") : "" } ?? ""))
                    if item.bits != nil || item.api != "Unknown" {
                        InfoRow(label: "Program type", value: [item.bits.map { "\($0)-bit" }, item.api == "Unknown" ? nil : item.api]
                            .compactMap { $0 }.joined(separator: " · "))
                    }
                    if item.size >= 0 { InfoRow(label: "Size", value: fmtBytes(item.size)) }
                    PathRow(label: "On your Mac", path: item.path)
                    if FileManager.default.fileExists(atPath: item.log) {
                        HStack {
                            Text("Last run's log").font(.subheadline)
                            Spacer()
                            Button("Open log") { NSWorkspace.shared.open(URL(fileURLWithPath: item.log)) }
                        }
                    }
                }
            }.padding(24)
        }
        .onAppear { args = item.args }
        .confirmationDialog("Move “\(item.name)” to the Trash?", isPresented: $confirmTrash) {
            Button("Move to Trash", role: .destructive) { Task { await model.act("Removing…", ["trash", item.id], thenItems: true) } }
        } message: { Text("It disappears from drive W:. Programs it installed on a C: drive stay installed.") }
        .confirmationDialog("Import “\(item.name)” into the Windows registry?", isPresented: $confirmReg) {
            Button("Import") { Task { await model.act("Importing…", ["regimport", item.id]) } }
        } message: { Text("Registry files change Windows settings for every program on the \(engineShort(item.effectiveEngine)) engine. Only import files you trust.") }
    }

    var subtitle: String {
        var parts = [kindInfo(item.kind).label, item.winPath]
        if item.running { parts.append("running") }
        return parts.joined(separator: " · ")
    }

    @ViewBuilder var actions: some View {
        HStack(spacing: 10) {
            switch item.kind {
            case "program", "folder":
                if item.running {
                    Button { Task { await model.act("Closing \(item.name)…", ["stop", item.id], thenItems: true) } } label: {
                        Label("Quit", systemImage: "stop.fill").frame(minWidth: 80)
                    }.buttonStyle(.borderedProminent).tint(.red).controlSize(.large)
                } else {
                    Button { Task { await model.act("Launching \(item.name)…", ["launch", item.id], thenItems: true) } } label: {
                        Label("Play", systemImage: "play.fill").frame(minWidth: 80)
                    }.buttonStyle(.borderedProminent).controlSize(.large)
                }
            case "installer":
                Button { Task { await model.act("Starting installer…", ["launch", item.id], thenItems: true) } } label: {
                    Label("Install", systemImage: "square.and.arrow.down").frame(minWidth: 80)
                }.buttonStyle(.borderedProminent).controlSize(.large).disabled(item.running)
            case "disk":
                if let d = item.diskLetter {
                    Button { Task { await model.act("Running setup…", ["disk-setup", item.id]) } } label: {
                        Label("Run setup from \(d)", systemImage: "play.fill")
                    }.buttonStyle(.borderedProminent).controlSize(.large)
                    Button { Task { await model.act("Ejecting…", ["unmount", item.id], thenItems: true) } } label: {
                        Label("Eject", systemImage: "eject")
                    }
                } else {
                    Button { Task { await model.act("Inserting disc…", ["mount", item.id], thenItems: true) } } label: {
                        Label("Insert disc", systemImage: "opticaldiscdrive")
                    }.buttonStyle(.borderedProminent).controlSize(.large)
                }
            case "archive":
                Button { Task { await model.act("Unpacking \(item.name)…", ["extract", item.id], thenItems: true) } } label: {
                    Label("Unpack", systemImage: "archivebox")
                }.buttonStyle(.borderedProminent).controlSize(.large)
            case "registry":
                Button { confirmReg = true } label: { Label("Import…", systemImage: "square.and.arrow.down.on.square") }
                    .buttonStyle(.borderedProminent).controlSize(.large)
            case "files":
                EmptyView()
            default:
                Button { Task { await model.act("Opening \(item.name)…", ["launch", item.id]) } } label: {
                    Label("Open in Windows", systemImage: "arrow.up.forward.app")
                }.buttonStyle(.borderedProminent).controlSize(.large)
            }
            Button { reveal(item.path) } label: { Label("Show in Finder", systemImage: "folder") }
            Spacer()
            Button(role: .destructive) { confirmTrash = true } label: { Image(systemName: "trash") }
                .help("Move to Trash").disabled(item.running)
        }
    }

    var engineHelp: String {
        switch item.effectiveEngine {
        case "d3dmetal":
            return "Wine 11 with Apple's D3DMetal: DirectX 11 and 12 straight to Metal, plus DLSS → MetalFX upscaling. The engine for DirectX 12 games. Same C: drive as Steam."
        default:
            return "Wine 11 with DXMT / DXVK: the newest Wine, best for DirectX 9–11 games and launchers. Shares the C: drive with Steam."
        }
    }

    func gfxHelp(_ m: String) -> String {
        switch m {
        case "dxmt": return "DXMT translates DirectX 10/11 straight to Metal. Fastest on Apple Silicon. Its DLLs are placed next to the program while this is selected."
        case "dxvk": return "DXVK translates DirectX 10/11 to Vulkan, and MoltenVK turns that into Metal. Slower, but a good fallback if a game glitches on DXMT."
        default: return "Wine's own DirectX (over OpenGL). Fine for DirectX 9 and older games; modern games won't start with it."
        }
    }
}

struct InfoRow: View {
    let label: String
    let value: String
    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label).font(.subheadline).frame(width: 110, alignment: .leading)
            Text(value).font(.callout.monospaced()).foregroundStyle(.secondary).textSelection(.enabled)
            Spacer()
        }
    }
}

// MARK: - This PC

struct ThisPCView: View {
    @EnvironmentObject var model: AppModel
    @State private var confirmKill = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Header(title: "This PC", subtitle: "The Windows side of your Mac: its drives, engines and what's running.")

                Card(title: "Drives", systemImage: "externaldrive") {
                    DriveRow(letter: "W:", name: "MacX", detail: "The folder on your Desktop. Anything you put in it is here.",
                             path: dropPath, ok: model.status?.dropExists ?? false)
                    ForEach(model.status?.engines.filter(\.ready) ?? []) { e in
                        Divider()
                        DriveRow(letter: "C:", name: "Windows (\(e.short))", detail: e.id == "wine11" ? "Steam, launchers and programs installed with Wine 11." : "Programs installed with the D3DMetal engine.",
                                 path: e.cDrive, ok: e.wDrive)
                    }
                    HStack {
                        Button { Task { await model.act("Opening W:…", ["tool", "explorer"]) } } label: {
                            Label("Open W: in Windows file manager", systemImage: "macwindow")
                        }
                        Button { openDesktop() } label: { Label("Windows desktop", systemImage: "rectangle.on.rectangle") }
                            .help("A Windows desktop in a window, with a taskbar and Start menu (Wine 11 engine).")
                    }
                }

                Card(title: "Engines", systemImage: "cpu") {
                    ForEach(model.status?.engines ?? []) { e in
                        HStack {
                            Image(systemName: e.available ? (e.ready ? "checkmark.circle.fill" : "circle.dashed") : "xmark.circle")
                                .foregroundStyle(e.available ? (e.ready ? .green : .orange) : .red)
                            VStack(alignment: .leading) {
                                Text(e.name)
                                Text(!e.available ? "Not installed" : (e.ready ? "Ready" : "Not set up yet"))
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            if e.available && !e.ready {
                                Button("Set up (about a minute)") { Task { await model.act("Setting up \(e.short)…", ["engine-setup", e.id]) } }
                            }
                        }
                    }
                    Text("Auto picks D3DMetal for DirectX 12 games and Wine 11 for everything else. You can override it per program.")
                        .font(.caption).foregroundStyle(.secondary)
                }

                Card(title: "Running now", systemImage: "play.rectangle") {
                    let items = model.status?.runningItems ?? []
                    let games = model.status?.runningGames ?? []
                    let procs = model.status?.processes ?? []
                    if items.isEmpty && games.isEmpty && procs.isEmpty {
                        Text("No Windows programs are running.").foregroundStyle(.secondary)
                    } else {
                        ForEach(items, id: \.self) { r in
                            HStack {
                                Label("W:\\\(r.id)  (\(r.exe), \(engineShort(r.engine)))", systemImage: "folder.fill").foregroundStyle(.green)
                                Spacer()
                                Button("Quit") { Task { await model.act("Closing…", ["stop", r.id], thenItems: true) } }
                            }
                        }
                        ForEach(games, id: \.self) { g in
                            Label("\(g.name)  (\(g.exe))", systemImage: "gamecontroller.fill").foregroundStyle(.green)
                        }
                        let names = Dictionary(grouping: procs, by: { $0.exe }).map { ($0.key, $0.value.count) }
                            .sorted { $0.0.lowercased() < $1.0.lowercased() }
                        Text(names.map { $0.1 > 1 ? "\($0.0) ×\($0.1)" : $0.0 }.joined(separator: " · "))
                            .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                    }
                    HStack {
                        Spacer()
                        Button(role: .destructive) { confirmKill = true } label: {
                            Label("Force quit all Windows programs", systemImage: "xmark.octagon")
                        }.disabled(procs.isEmpty)
                    }
                }

                Card(title: "Disk space", systemImage: "internaldrive") {
                    if let s = model.status {
                        let used = Double(s.totalBytes - s.freeBytes) / Double(max(s.totalBytes, 1))
                        ProgressView(value: used).tint(s.freeBytes < 25_000_000_000 ? .orange : .accentColor)
                        Text("\(fmtBytes(s.freeBytes)) free of \(fmtBytes(s.totalBytes))")
                            .font(.callout).foregroundStyle(s.freeBytes < 25_000_000_000 ? .orange : .secondary)
                    }
                }

                Card(title: "Options", systemImage: "slider.horizontal.3") {
                    Toggle("Show FPS overlay in games (Apple's Metal HUD)", isOn: Binding(
                        get: { model.status?.hud ?? false },
                        set: { v in Task { await model.act("Saving…", ["hud", v ? "on" : "off"]) } }))
                    Text("Applies to programs started from here from now on, and to Steam after it restarts.")
                        .font(.caption).foregroundStyle(.secondary)
                    Button { Task { await model.repair() } } label: { Label("Check & repair setup", systemImage: "stethoscope") }
                }
            }
            .padding(24)
        }
        .confirmationDialog("Force quit every Windows program, including Steam and any game?", isPresented: $confirmKill) {
            Button("Force Quit All", role: .destructive) { Task { await model.act("Force quitting…", ["killall"], thenItems: true) } }
        } message: { Text("Unsaved game progress will be lost.") }
    }

    func openDesktop() {
        let f = NSScreen.main?.visibleFrame.size ?? CGSize(width: 1600, height: 1000)
        let size = "\(Int(f.width * 0.85))x\(Int(f.height * 0.85))"
        Task { await model.act("Opening the Windows desktop…", ["desktop", "wine11", size]) }
    }
}

struct DriveRow: View {
    let letter: String
    let name: String
    let detail: String
    let path: String
    let ok: Bool
    var body: some View {
        HStack(spacing: 12) {
            Text(letter).font(.title2.weight(.bold).monospaced()).frame(width: 44)
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(.headline)
                Text(detail).font(.caption).foregroundStyle(.secondary)
                if !ok { Text("Not connected. Use Check & repair.").font(.caption).foregroundStyle(.orange) }
            }
            Spacer()
            Button { reveal(path) } label: { Image(systemName: "arrow.up.forward.square") }.buttonStyle(.borderless)
                .help("Show in Finder")
        }
    }
}

// MARK: - Programs (Start Menu)

struct ProgramsView: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Header(title: "Programs", subtitle: "What's installed on the C: drives: the Windows Start menu.")
                    Spacer()
                    Button { Task { await model.refreshPrograms() } } label: { Label("Refresh", systemImage: "arrow.clockwise") }
                }
                let byEngine = Dictionary(grouping: model.programs, by: { $0.engine })
                ForEach(["d3dmetal", "wine11", "gptk77"], id: \.self) { eid in
                    if let list = byEngine[eid], !list.isEmpty {
                        Card(title: "Installed with \(engineShort(eid))", systemImage: "square.grid.2x2") {
                            ForEach(list) { p in
                                HStack {
                                    VStack(alignment: .leading, spacing: 1) {
                                        Text(p.name).font(.headline)
                                        if !p.folder.isEmpty { Text(p.folder).font(.caption).foregroundStyle(.secondary) }
                                    }
                                    Spacer()
                                    Button { Task { await model.act("Starting \(p.name)…", ["run-lnk", p.engine, p.path]) } } label: {
                                        Label("Open", systemImage: "play.fill")
                                    }
                                }
                                if p != list.last { Divider() }
                            }
                        }
                    }
                }
                if model.programs.isEmpty {
                    Text("Nothing installed yet. Put an installer in the MacX folder and press Install.")
                        .foregroundStyle(.secondary)
                }
            }.padding(24)
        }
        .onAppear { Task { await model.refreshPrograms() } }
    }
}

// MARK: - Steam

struct GamesView: View {
    @EnvironmentObject var model: AppModel
    @State private var selected: String?
    @State private var newAppId = ""

    var body: some View {
        HSplitView {
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    Circle().fill(model.status?.steamRunning ?? false ? Color.green : Color.secondary.opacity(0.5)).frame(width: 8, height: 8)
                    Text(model.status?.steamRunning ?? false ? "Steam running" : "Steam stopped").font(.callout)
                    Spacer()
                    if model.status?.steamRunning ?? false {
                        Button("Show") { Task { await model.act("Showing Steam…", ["steam", "start"]) } }
                        Button("Quit") { Task { await model.act("Closing Steam…", ["steam", "stop"]) } }
                    } else {
                        Button("Start Steam") { Task { await model.act("Starting Steam…", ["steam", "start"]) } }
                    }
                }.padding(12)
                Divider()
                List(selection: $selected) {
                    Section("Installed in Steam (Windows)") {
                        ForEach(model.games) { g in
                            VStack(alignment: .leading, spacing: 3) {
                                Text(g.name).font(.headline)
                                HStack(spacing: 6) {
                                    Text(fmtBytes(g.size))
                                    Badge(text: modeName(g.mode))
                                    if g.state != "Installed" { Text(g.state).foregroundStyle(.orange) }
                                }.font(.caption).foregroundStyle(.secondary)
                            }.padding(.vertical, 3).tag(g.appid)
                        }
                    }
                }
                Divider()
                VStack(alignment: .leading, spacing: 6) {
                    Text("Install another game").font(.subheadline.weight(.semibold))
                    HStack {
                        TextField("Steam App ID, e.g. 3240220", text: $newAppId).textFieldStyle(.roundedBorder)
                        Button("Install") {
                            let id = newAppId.trimmingCharacters(in: .whitespaces)
                            Task { await model.act("Asking Steam to install…", ["install", id], thenGames: true) }
                        }.disabled(newAppId.isEmpty)
                    }
                    Text("The App ID is the number in the game's Steam store link. Games installed from Steam's own Library show up here automatically.")
                        .font(.caption).foregroundStyle(.secondary)
                }.padding(12)
            }
            .frame(minWidth: 260, idealWidth: 300, maxWidth: 380)

            Group {
                if let g = model.games.first(where: { $0.appid == selected }) {
                    GameDetail(game: g).id(g.appid)
                } else {
                    VStack(spacing: 10) {
                        Image(systemName: "gamecontroller").font(.system(size: 40)).foregroundStyle(.secondary)
                        Text(model.games.isEmpty ? "No Steam games installed yet." : "Select a game.")
                            .foregroundStyle(.secondary)
                    }.frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .frame(minWidth: 480, maxWidth: .infinity, maxHeight: .infinity)
        }
        .onAppear {
            Task { await model.refreshGames() }
            if selected == nil { selected = model.games.first?.appid }
        }
        .onChange(of: model.games) { _, games in if selected == nil { selected = games.first?.appid } }
    }
}

func modeName(_ m: String) -> String {
    switch m {
    case "dxmt": return "DXMT"
    case "dxvk": return "DXVK"
    default: return "D3DMetal"
    }
}

struct GameDetail: View {
    @EnvironmentObject var model: AppModel
    let game: Game
    @State private var mode: String = "dxmt"
    @State private var exe: String = ""
    @State private var opts: String = ""
    @State private var confirmUninstall = false
    @State private var confirmForce = false

    var isRunning: Bool { model.status?.runningGames.contains { $0.name == game.name } ?? false }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(game.name).font(.largeTitle.weight(.semibold))
                    Text("\(fmtBytes(game.size)) · \(game.state) · Steam App ID \(game.appid)")
                        .foregroundStyle(.secondary)
                }
                HStack(spacing: 10) {
                    Button { Task { await model.act("Launching \(game.name)…", ["play", game.appid]) } } label: {
                        Label(isRunning ? "Running" : "Play", systemImage: "play.fill").frame(minWidth: 80)
                    }.buttonStyle(.borderedProminent).controlSize(.large).disabled(isRunning)
                    Button { reveal(game.path) } label: { Label("Show files", systemImage: "folder") }
                    Button(role: .destructive) { confirmUninstall = true } label: { Label("Uninstall…", systemImage: "trash") }
                    Menu {
                        Button("Remove files without Steam (moves to Trash)…") { confirmForce = true }
                    } label: { Image(systemName: "ellipsis.circle") }.menuStyle(.borderlessButton).frame(width: 30)
                }

                Card(title: "Graphics (DirectX translation)", systemImage: "cpu") {
                    Picker("", selection: $mode) {
                        Text("DXMT → Metal").tag("dxmt")
                        Text("DXVK → Vulkan → Metal").tag("dxvk")
                        Text("D3DMetal").tag("wine")
                    }.pickerStyle(.segmented).labelsHidden()
                    Text(modeHelp(mode)).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    if game.dx12 {
                        Label("DirectX 12 game: pick D3DMetal (Apple's DirectX 12 → Metal translator). Steam runs on the D3DMetal-enabled Wine 11.", systemImage: "info.circle")
                            .font(.callout).foregroundStyle(.secondary)
                    }
                    HStack {
                        Text("Currently: \(modeName(game.mode))").font(.caption).foregroundStyle(.secondary)
                        Spacer()
                        Button("Apply") { Task { await model.act("Switching graphics…", ["gfx", game.appid, mode], thenGames: true) } }
                            .disabled(mode == game.mode || isRunning)
                    }
                }

                Card(title: "Main program", systemImage: "app") {
                    Picker("Program the graphics setting applies to", selection: $exe) {
                        ForEach(game.exes, id: \.self) { Text($0).tag($0) }
                    }
                    HStack {
                        Text("Usually the game's own .exe (for GTA V: GTA5.exe). Change only if a game starts through a different program.")
                            .font(.caption).foregroundStyle(.secondary)
                        Spacer()
                        Button("Save") { Task { await model.act("Saving…", ["set-exe", game.appid, exe], thenGames: true) } }
                            .disabled(exe == (game.mainExe ?? ""))
                    }
                }

                Card(title: "Launch options", systemImage: "terminal") {
                    TextField("e.g. -nobattleye", text: $opts).textFieldStyle(.roundedBorder).font(.system(.body, design: .monospaced))
                    HStack {
                        Text("Same as Steam's Properties → Launch Options. Saving closes and reopens Steam if it's open.")
                            .font(.caption).foregroundStyle(.secondary)
                        Spacer()
                        Button("Save") { Task { await model.act("Saving launch options…", ["launchopts", game.appid, opts], thenGames: true) } }
                            .disabled(opts == game.launchOptions)
                    }
                }

                Card(title: "Where it lives", systemImage: "mappin.and.ellipse") {
                    PathRow(label: "Game files", path: game.path)
                    Text("Inside Windows this is C:\\Program Files (x86)\\Steam\\steamapps\\common\\\(game.installdir)")
                        .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                }
            }.padding(24)
        }
        .onAppear { mode = game.mode; exe = game.mainExe ?? ""; opts = game.launchOptions }
        .confirmationDialog("Uninstall \(game.name)?", isPresented: $confirmUninstall) {
            Button("Uninstall through Steam", role: .destructive) {
                Task { await model.act("Asking Steam…", ["uninstall", game.appid], thenGames: true) }
            }
        } message: { Text("Steam will open and ask you to confirm. This frees about \(fmtBytes(game.size)).") }
        .confirmationDialog("Remove \(game.name)'s files without Steam?", isPresented: $confirmForce) {
            Button("Move to Trash", role: .destructive) {
                Task { await model.act("Removing…", ["uninstall-force", game.appid], thenGames: true) }
            }
        } message: { Text("Use this only if Steam's uninstall doesn't work. Steam must be closed. Space is freed when you empty the Trash.") }
    }

    func modeHelp(_ m: String) -> String {
        switch m {
        case "dxmt": return "Translates DirectX 11 straight to Metal. Usually the fastest on Apple Silicon. Recommended for GTA V Legacy."
        case "dxvk": return "Translates DirectX 9/10/11 to Vulkan, which MoltenVK turns into Metal. Very compatible; try it if a game glitches or crashes on DXMT."
        default: return "Apple's D3DMetal translates DirectX 11 and 12 straight to Metal, with DLSS → MetalFX upscaling. Required for DirectX 12 games like GTA V Enhanced."
        }
    }
}

struct PathRow: View {
    let label: String
    let path: String
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(label).font(.subheadline)
                Text(path.replacingOccurrences(of: NSHomeDirectory(), with: "~"))
                    .font(.caption.monospaced()).foregroundStyle(.secondary).textSelection(.enabled).lineLimit(2)
            }
            Spacer()
            Button { reveal(path) } label: { Image(systemName: "arrow.up.forward.square") }.help("Show in Finder")
        }
    }
}

// MARK: - Storage

let storageGroups = ["MacX folder (W:)", "Games", "Windows side (C: drive)", "Engine", "Leftovers (safe to remove)"]

struct StorageView: View {
    @EnvironmentObject var model: AppModel
    @State private var toTrash: StorageItem?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Header(title: "Storage", subtitle: "What the Windows side uses on your Mac, and what you can safely remove.")
                    Spacer()
                    Button { Task { await model.refreshStorage() } } label: { Label("Refresh", systemImage: "arrow.clockwise") }
                        .disabled(model.storageLoading)
                }
                if model.storageLoading && model.storage.isEmpty {
                    HStack { ProgressView().controlSize(.small); Text("Measuring folders (big games take a few seconds)…") }
                }
                if let s = model.status {
                    Card(title: "Free space", systemImage: "internaldrive") {
                        ProgressView(value: Double(s.totalBytes - s.freeBytes) / Double(max(s.totalBytes, 1)))
                        Text("\(fmtBytes(s.freeBytes)) free of \(fmtBytes(s.totalBytes)). Things you move to the Trash still use space until you empty the Trash.")
                            .font(.callout).foregroundStyle(.secondary)
                    }
                }
                let groups = Dictionary(grouping: model.storage, by: { $0.group })
                ForEach(storageGroups, id: \.self) { group in
                    if let items = groups[group], !items.isEmpty {
                        let total = items.reduce(Int64(0)) { $0 + $1.size }
                        let sorted = items.sorted { $0.size > $1.size }
                        Card(title: "\(group) — \(fmtBytes(total))", systemImage: groupIcon(group)) {
                            ForEach(sorted) { item in
                                HStack(alignment: .top) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        HStack { Text(item.name).font(.subheadline.weight(.medium)); Spacer(); Text(fmtBytes(item.size)).monospacedDigit() }
                                        Text(item.note).font(.caption).foregroundStyle(.secondary)
                                        Text(item.path.replacingOccurrences(of: NSHomeDirectory(), with: "~"))
                                            .font(.caption2.monospaced()).foregroundStyle(.tertiary).textSelection(.enabled)
                                    }
                                    Button { reveal(item.path) } label: { Image(systemName: "arrow.up.forward.square") }
                                        .buttonStyle(.borderless).help("Show in Finder")
                                    if item.removable {
                                        Button(role: .destructive) { toTrash = item } label: { Image(systemName: "trash") }
                                            .buttonStyle(.borderless).help("Move to Trash")
                                    }
                                }
                                if item != sorted.last { Divider() }
                            }
                        }
                    }
                }
            }.padding(24)
        }
        .onAppear { if model.storage.isEmpty { Task { await model.refreshStorage() } } }
        .confirmationDialog("Move “\(toTrash?.name ?? "")” to the Trash?", isPresented: Binding(
            get: { toTrash != nil }, set: { if !$0 { toTrash = nil } })) {
            Button("Move to Trash", role: .destructive) {
                if let item = toTrash {
                    do {
                        try FileManager.default.trashItem(at: URL(fileURLWithPath: item.path), resultingItemURL: nil)
                        model.show("Moved \(item.name) to the Trash. Empty the Trash to free \(fmtBytes(item.size)).")
                    } catch {
                        model.show("Couldn't move it: \(error.localizedDescription)", error: true)
                    }
                    Task { await model.refreshStorage() }
                }
                toTrash = nil
            }
        } message: { Text(toTrash?.note ?? "") }
    }

    func groupIcon(_ g: String) -> String {
        switch g {
        case "Games": return "gamecontroller"
        case "Engine": return "gearshape.2"
        case "Leftovers (safe to remove)": return "sparkles"
        case "MacX folder (W:)": return "folder.fill"
        default: return "externaldrive"
        }
    }
}

// MARK: - Tools

struct ToolsView: View {
    @EnvironmentObject var model: AppModel
    @State private var engine = "wine11"

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Header(title: "Tools", subtitle: "Windows utilities, and fixes for when things go wrong.")

                Card(title: "Run a Windows program from anywhere", systemImage: "play.square") {
                    Text("Runs a .exe or .msi without adding it to W:. Auto picks the engine. Tip: in Finder, right-click any .exe → Open With → MacX does the same.")
                        .font(.callout).foregroundStyle(.secondary)
                    Button { pickExe() } label: { Label("Choose a .exe or .msi…", systemImage: "doc.badge.plus") }
                }

                Card(title: "Windows utilities", systemImage: "macwindow") {
                    Picker("Engine", selection: $engine) {
                        Text("Wine 11").tag("wine11")
                        Text("D3DMetal").tag("d3dmetal")
                    }.pickerStyle(.segmented).frame(maxWidth: 260)
                    HStack {
                        Button("File manager (W:)") { tool("explorer") }
                        Button("Control panel") { tool("control") }
                        Button("Wine settings") { tool("winecfg") }
                        Button("Registry editor") { tool("regedit") }
                        Button("Task manager") { tool("taskmgr") }
                        Button("Command prompt") { tool("cmd") }
                    }
                    Text("Each engine has its own C: drive and registry, so settings changed here only affect the engine picked above.")
                        .font(.caption).foregroundStyle(.secondary)
                }

                Card(title: "Check & repair", systemImage: "stethoscope") {
                    Text("Verifies both engines, the W: drive link, the Mac-driver patch, DXMT/DXVK files and the window fixes for Steam and the Rockstar launcher, and re-applies anything an update overwrote.")
                        .font(.callout).foregroundStyle(.secondary)
                    Button { Task { await model.repair() } } label: { Label("Run checks", systemImage: "checkmark.shield") }
                    ForEach(model.checks, id: \.self) { c in
                        Label(c.name, systemImage: c.status == "problem" ? "xmark.circle.fill" : "checkmark.circle.fill")
                            .foregroundStyle(c.status == "problem" ? .red : (c.status == "fixed" ? .orange : .green))
                    }
                }

                Card(title: "Logs", systemImage: "doc.text.magnifyingglass") {
                    ForEach(model.paths.filter { $0.name.lowercased().contains("log") }, id: \.self) { p in
                        HStack {
                            Text(p.name)
                            Spacer()
                            Button("Open") { NSWorkspace.shared.open(URL(fileURLWithPath: p.path)) }
                            Button { reveal(p.path) } label: { Image(systemName: "arrow.up.forward.square") }.buttonStyle(.borderless)
                        }
                    }
                }

            }.padding(24)
        }
    }

    func tool(_ name: String) {
        Task { await model.act("Opening…", ["tool", name, engine]) }
    }

    func pickExe() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = ["exe", "msi"].compactMap { UTType(filenameExtension: $0) }
        panel.allowsOtherFileTypes = true
        panel.canChooseDirectories = false
        if panel.runModal() == .OK, let url = panel.url {
            Task { await model.act("Starting \(url.lastPathComponent)…", ["open", url.path]) }
        }
    }
}

// MARK: - Help

struct HelpView: View {
    @EnvironmentObject var model: AppModel
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Header(title: "Help", subtitle: "How MacX works, in plain words.")

                HelpCard(title: "The MacX folder", icon: "folder.fill", text: """
                The folder on your Desktop is a Windows drive. Inside Windows it's W:, and its name shows as “MacX”. Put anything in it, by dragging in Finder or dropping onto this app, and it shows up here right away:
                • A .exe, or a game's folder → Play
                • setup.exe, an installer or .msi → Install (onto a C: drive; then it's under Programs)
                • .iso disc image → Insert disc (it becomes a CD drive like D:)
                • .zip / .7z / .rar → Unpack
                • .lnk shortcuts, .bat scripts, .reg files → open, run, import
                Games keep their files and saves where they are, so a game folder you copy in plays straight from W:.
                """)
                HelpCard(title: "Two engines", icon: "cpu", text: """
                • Wine 11 + DXMT/DXVK: the newest Wine. Best for DirectX 9–11 games, launchers and Steam. Uses the C: drive with Steam on it.
                • D3DMetal: the same Wine 11 with Apple's D3DMetal (from Game Porting Toolkit 3.0) bridged in. Translates DirectX 11 and 12 straight to Metal, and DLSS to MetalFX. The route for DirectX 12 games. Shares the C: drive with Steam, and Steam itself runs on it.
                Auto reads each program file to see which DirectX it uses, and picks D3DMetal for DirectX 12.
                """)
                HelpCard(title: "Graphics translators, measured on this Mac", icon: "speedometer", text: """
                Same DirectX 11 test program, Apple M4, frames per second (higher is better):
                • DXMT (DirectX 11 → Metal): about 850
                • D3DMetal (DirectX 11/12 → Metal): about 790, and it also runs DirectX 12 (about 560 in the DirectX 12 test)
                • DXVK (DirectX 11 → Vulkan → MoltenVK → Metal): about 115
                • Wine built-in: fast on this simple test but only offers DirectX 9-level features, so modern games won't start.
                The test only clears the screen, so it measures overhead, not a real game. It still shows the pattern: going straight to Metal beats the extra Vulkan step.
                """)
                HelpCard(title: "Opening .exe files from Finder", icon: "cursorarrow.click.2", text: """
                Right-click any .exe → Open With → MacX. To make that the default, use Get Info → Open with → MacX → Change All.
                """)
                HelpCard(title: "If something breaks", icon: "lifepreserver", text: """
                1. This PC → Force quit all Windows programs, then try again.
                2. Open the program's log (Details → Open log).
                3. Switch its engine (Wine 11 ↔ D3DMetal), or on Wine 11 switch graphics (DXMT ↔ DXVK).
                4. Tools → Run checks.
                """)
                Card(title: "Where everything lives", systemImage: "map") {
                    ForEach(model.paths.filter { !$0.name.lowercased().contains("log") }, id: \.self) { p in
                        PathRow(label: p.name, path: p.path)
                    }
                }
            }.padding(24)
        }
    }
}

struct HelpCard: View {
    let title: String
    let icon: String
    let text: String
    var body: some View {
        Card(title: title, systemImage: icon) {
            Text(text).font(.callout).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
        }
    }
}

// MARK: - First-run setup

struct SetupView: View {
    @EnvironmentObject var model: AppModel
    @State private var checks: [PreCheck] = []
    @State private var progress: InstallStatus?
    @State private var installing = false
    @State private var poll: Timer?

    var ready: Bool { !checks.isEmpty && checks.allSatisfy(\.ok) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Header(title: "Set up MacX",
                       subtitle: "Builds the Windows side of your Mac: Wine 11, Apple's D3DMetal (DirectX 11/12 → Metal), and a Windows C: drive. About 1.5 GB, a few minutes.")
                Card(title: "This Mac", systemImage: "checklist") {
                    if checks.isEmpty { HStack { ProgressView().controlSize(.small); Text("Checking…") } }
                    ForEach(checks, id: \.self) { c in
                        VStack(alignment: .leading, spacing: 3) {
                            Label(c.name + (c.detail.isEmpty ? "" : " — " + c.detail),
                                  systemImage: c.ok ? "checkmark.circle.fill" : "xmark.circle.fill")
                                .foregroundStyle(c.ok ? .green : .red)
                            if !c.ok && !c.fix.isEmpty {
                                Text(c.fix).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
                                    .padding(.leading, 26)
                            }
                        }
                    }
                    HStack {
                        Spacer()
                        Button("Check again") { Task { await runChecks() } }.disabled(installing)
                    }
                }
                Card(title: "Install", systemImage: "square.and.arrow.down") {
                    if let p = progress, installing || p.error != nil {
                        let steps = p.steps ?? []
                        ForEach(Array(steps.enumerated()), id: \.offset) { i, name in
                            let idx = p.stepIndex ?? 0
                            Label(name, systemImage: i < idx || p.done ? "checkmark.circle.fill" : (i == idx ? "circle.dotted" : "circle"))
                                .foregroundStyle(i < idx || p.done ? .green : (i == idx ? .primary : .secondary))
                        }
                        if let f = p.fraction, !p.done { ProgressView(value: f) }
                        if let d = p.detail, !d.isEmpty { Text(d).font(.caption).foregroundStyle(.secondary) }
                        if let e = p.error { Text(e).foregroundStyle(.red).textSelection(.enabled) }
                    } else {
                        Text("Downloads are pinned and checksum-verified: Gcenx's Wine 11 build, DXVK-macOS and DXMT. D3DMetal is copied from your own Game Porting Toolkit; nothing from Apple is downloaded or shipped by this app.")
                            .font(.callout).foregroundStyle(.secondary)
                    }
                    HStack {
                        Spacer()
                        Button(installing ? "Installing…" : (progress?.error != nil ? "Try again" : "Install")) { install() }
                            .buttonStyle(.borderedProminent).controlSize(.large).disabled(!ready || installing)
                    }
                }
            }.padding(24).frame(maxWidth: 760)
        }
        .task { await runChecks() }
    }

    func runChecks() async {
        checks = await Backend.call(PreflightResp.self, ["preflight"])?.checks ?? []
    }

    func install() {
        installing = true
        progress = nil
        poll = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
            Task { @MainActor in progress = await Backend.call(InstallStatus.self, ["install-status"]) }
        }
        Task {
            let r = await Backend.call(MsgResp.self, ["install"])
            poll?.invalidate()
            progress = await Backend.call(InstallStatus.self, ["install-status"])
            installing = false
            if r?.ok == true {
                model.show(r?.message ?? "Ready.")
                await model.refreshAll()
            }
        }
    }
}

// MARK: - Building blocks

struct Header: View {
    let title: String
    let subtitle: String
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.largeTitle.weight(.semibold))
            Text(subtitle).foregroundStyle(.secondary)
        }
    }
}

struct Card<Content: View>: View {
    let title: String
    let systemImage: String
    @ViewBuilder var content: Content
    var body: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 10) { content }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(6)
        } label: {
            Label(title, systemImage: systemImage).font(.headline)
        }
    }
}
