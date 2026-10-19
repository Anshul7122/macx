# MacX user guide

This guide is for players, not programmers. It explains how to get a Windows game from "a file I have" to
"running on my Mac", and what to do when something doesn't work.

## The idea in one paragraph

Windows games can't run on a Mac by themselves. MacX runs them inside **Wine**, a free program that pretends to
be Windows, and translates their graphics (Microsoft's **DirectX**) into Apple's graphics system (**Metal**).
MacX keeps each "Windows PC" in a **box**: an ordinary folder in `MacX Boxes` in your home folder. Whatever
you put in a box, and whatever gets installed into it, stays inside that folder. Throw the folder away and the
whole Windows PC is gone, with nothing left behind.

## 1. Install MacX

1. Open `MacX-0.2.0.dmg` and drag **MacX** into Applications.
2. The first time, right-click MacX → **Open** → **Open** (MacX isn't from the App Store, so macOS asks once).
3. The setup screen checks your Mac and installs what it needs (a few minutes). You need Apple's free **Game
   Porting Toolkit** installed first; the setup screen tells you if it's missing.

## The quickest way: the "MacX Games" folder on your Desktop

MacX puts a folder called **MacX Games** on your Desktop. It's a ready-made box made for downloads:

1. **Download the game straight into it** (save the download there, or drag it in). Files still downloading
   are ignored until they're complete.
2. **Start it**: double-click the installer (`setup.exe`) in Finder, or open MacX → Boxes → *MacX Games* and
   press **Install** (or **Set Up All**). Archives are unpacked and discs inserted first, automatically.
3. **Click through the installer** as on Windows. It's already set to install the game **into this same
   folder** (for example `MacX Games/Game Name`); you can change that on its folder page if you want.
4. When it's done, the game appears in MacX under *Games & programs*. Press **Play**.
5. You can now **delete the download package** (the installer and its `.bin` files); the installed game folder
   is all you need.

If a game's window opens but doesn't react, or a benchmark stops by itself straight away, **click once into the
game's window**: macOS doesn't always hand the focus to a game that a launcher started.

## 2. Make a box

Open MacX. It starts on the **Boxes** page. Press **New Box**. A folder called *Box 1* appears in
`MacX Boxes` (in your home folder). Rename it in Finder if you like.

> One box can hold many games. Use separate boxes when you want things kept apart, e.g. one per game
> launcher, or one for trying out something you're not sure about.

## 3. Put games in it — any number, any kind

Three ways, all doing the same thing:

- Press **Add Files…** and pick as many files or folders as you want (hold ⌘ to pick several).
- Drag them from Finder onto the box in MacX (onto the box's name on the left, or onto the big area on the right).
- Drag them into the box's folder in Finder.

What you can add:

| You have | Example | What happens |
| --- | --- | --- |
| A game folder | `My Game/` with `MyGame.exe` inside | Ready to play straight away |
| A single program | `Game.exe` | Ready to play straight away |
| An installer | `setup.exe`, or a folder with `setup.exe` + `data-1.bin`, `data-2.bin`…, or an `.msi` | Gets installed |
| An archive | `.zip`, `.7z`, `.rar`, or a split one: `.7z.001`, `.7z.002`… (add all the parts) | Gets unpacked, then whatever was inside gets set up too |
| A disc image | `.iso` | Gets "inserted" as drive D: and its setup runs |

Copying is instant when the file is on the same disk as your home folder, and takes no extra space.

## 4. Press "Set Up All"

When a box has things that need installing or unpacking, a blue **Set Up All** button appears. Press it.
MacX goes through them **one at a time** and shows its progress in an orange bar:

- Archives are unpacked into a folder next to them.
- Discs are inserted and their setup program starts.
- **Installers open their own window, just like on Windows.** Click through them as you normally would
  (Next → Install → Finish). Keep the suggested install folder unless you have a reason to change it.

When you add files through MacX, Set Up starts by itself. Each item then shows **Installed** or
**Unpacked** (or an error message; see "When something goes wrong").

**Installers MacX didn't recognise.** MacX spots installers by their name (`setup…`, `install…`) and by what
they're made with (Inno Setup, which most repacks use, NSIS, InstallShield, Microsoft's installers…). If an
installer still shows up as a game, open its **⋯** menu → **Treat as an Installer**. If something was wrongly
taken for an installer, use **⋯** → **Treat as a Program** under *Installers, archives & discs*.

**Installing without clicking.** In an installer's **⋯** menu → **Install Options…** you can give it options,
as you would on Windows: `/VERYSILENT` for Inno Setup installers (most repacks), `/S` for NSIS ones, `/quiet` for
Microsoft ones. Not every installer listens to these; those simply open their window as usual.

## 5. Play

Everything playable is listed under **Games & programs**: games that got installed (MacX finds their
Start Menu and Desktop shortcuts, like Windows does) and games that were already ready to play. Press
**Play**. The first start of a game can take a minute; later starts are faster.

While a game runs, its row says **Running** and the button becomes **Stop**. **Stop All** at the top closes
everything in that box. **Close games when you're done** — a running game keeps the Mac working (and warm)
even in the background.

### The graphics menu next to each game

MacX picks the best way to get the game's graphics onto Metal. You normally leave it on **Auto**; the word
in brackets shows what Auto chose.

| Choice | Best for | In plain words |
| --- | --- | --- |
| **D3DMetal** | most modern games (64-bit, DirectX 11 or 12) | Apple's own translator. What GTA V Enhanced uses. |
| **DXMT** | older or 32-bit games using DirectX 10/11 | A free translator that goes straight to Metal and also handles 32-bit games. |
| **Wine** | very old games (DirectX 9 and earlier), OpenGL and Vulkan games | Wine's built-in route. |

If a game shows a black screen or closes right away, try the other choices one by one.

### Getting the best frame rate

- **macOS Game Mode doesn't switch on for Windows games yet.** macOS only gives it to apps that declare
  themselves games, and a running Windows game shows up as an anonymous "Wine" process. Fixing this is on the
  list for a later version; until then, quit other heavy apps while you play.
- **Play full screen**: it's smoother than a window.
- **Keep the Mac cool and plugged in.** Apple chips slow themselves down when they get hot; that's the biggest
  difference between 45 and 60 fps in GTA V. A cool surface or a stand with a fan helps. Turn off Low Power Mode.
- **Use the game's upscaling.** In the game's graphics settings choose **FSR** (or **DLSS** if offered, which
  MacX turns into Apple's MetalFX). The game draws fewer pixels and scales them up: more fps, less heat.
- **Cap the frame rate** in the game (for example at 60). Frames above what you need just make heat.
- **Turn ray tracing off** and leave shadows/reflections at medium; they cost the most on Apple chips.
- The small **frame-rate overlay** (top-right corner of games) can be switched off on the **This PC** page; it
  costs very little, but nothing is free.
- Boxes don't slow games down: the sandbox only checks file access, which games do little of while playing.

## 6. Your Steam games (GTA V and others)

The **Steam** page keeps working as before. On the Boxes page there are also two links:

- **Copy my Steam setup into a box** — makes a box that starts with your current Steam, its games and saves.
  It's instant and uses no extra disk space (macOS shares the files until one side changes), and your
  original setup is not touched. In that box, Steam games are listed and **Play** starts them through Steam.
- **Move my existing setup into a box** — moves it instead of copying. Only if you want everything in boxes.

Quit Steam before using either.

## 7. When something goes wrong

- **Every item has a Log button** (and the ••• menu at the top → **Show Logs** opens the folder). The log is
  what Wine printed while running the installer or game. Useful when asking for help.
- **"Setup ended with error code …"**: the installer reported a problem. Press **Install Again**. Some
  "repack" installers need a lot of memory; close other apps first.
- **An installer crashes straight away**: some older installers don't run under Wine. If it's an Inno Setup
  installer (most repacks and GOG installers are) and the free tool *innoextract* is installed
  (`brew install innoextract`), MacX unpacks it instead, automatically; the game then appears as a folder ready
  to play. (Shortcuts and extras the installer would have made are skipped.)
- **A game's own launcher window stays empty or invisible**: some launchers don't draw under Wine. Open the
  game's **⋯** menu → **Program & Launch Options…**, pick the game's actual program (often in a `bin` folder)
  and, if the game needs them, its options.
- **Microsoft Visual C++ installers** (`VC_redist…exe`, often bundled with games) fail under Wine. That's
  harmless: Wine already contains those files, so the game itself still runs.
- **macOS asks whether MacX may access your Desktop folder**: click **Allow**. The older *MacX Drive* folder
  lives on the Desktop; boxes don't need it.
- **An archive won't unpack**: multi-part RAR files (`.part1.rar`, `.part2.rar`) must be unpacked with an app
  like *The Unarchiver* or *Keka* first; then add the unpacked folder.
- **The game doesn't appear after installing**: MacX looks for the game's shortcuts and for Windows' list of
  installed programs; a few installers make neither. Press **Install Again** and, when the installer asks
  where to install, choose a folder on drive **W:** (for example `W:\Games\My Game`). Anything on W: that
  contains a game `.exe` is listed by itself.
- **A game starts but looks wrong**: change the graphics menu (section 5).
- **Online games with anti-cheat** (BattlEye, Easy Anti-Cheat, Vanguard, Ricochet) won't work in any Wine-based
  tool. Story / single-player modes sometimes do.

## 8. Delete a box

Drag the box's folder to the Trash in Finder, or use ••• → **Delete Box…** in MacX. Either way MacX stops
whatever was running in it, ejects its discs and cleans up. Nothing from the box stays on your Mac (apart from
macOS's shared graphics cache, which macOS manages itself).

## 9. What a box keeps out

Programs in a box see only their own C: drive, the box folder (drive W:) and inserted discs. They can't see
or change the rest of your Mac's files: MacX runs them inside a macOS "sandbox" that blocks your home folder,
except the box itself. They can still use the internet, your graphics chip, sound and controllers, as games
need. This keeps ordinary programs in their place; it isn't a virus scanner, so only run things you trust.

## 10. Try it without any games

The project comes with six small test "games" in every supported form (an installer with data parts, a disc
image, a zip, a 7z, a split archive and a single exe). Each one draws a coloured window for 8 seconds and
writes its frame rate to `result.txt` next to itself. To build them (needs `python3 -m pip install ziglang`):

```bash
scripts/make-test-fixtures.sh
```

Then add everything in `build/fixtures` to a new box and press **Set Up All**.
