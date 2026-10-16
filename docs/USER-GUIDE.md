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
