// A stand-in for a "repack"-style game installer, used to test MacX without real game files.
//
// Like Inno Setup repacks it is a 32-bit setup.exe that sits next to data-1.bin, data-2.bin, ... (one archive
// split into parts), installs to C:\Games\<Game> by default (/DIR="..." changes it, /SILENT and /VERYSILENT hide
// the window), creates Start Menu and Desktop shortcuts, and registers an uninstall entry (a 32-bit installer
// writes it under Wow6432Node, as real ones do). The archive format is made by engine/tests/mxpack.py:
//   "MXPK" u32 version | u32 len, game name | u32 len, main exe (relative) | u32 count |
//   count x (u32 len, relative path with '\' | u64 size | bytes)            all strings UTF-8, little endian
#define COBJMACROS
#include <windows.h>
#include <shlobj.h>
#include <shobjidl.h>
#include <objbase.h>
#include <stdio.h>
#include <string.h>

static wchar_t g_dir[MAX_PATH];           // folder setup.exe is in
static int g_part = 0;                    // current data-N.bin
static HANDLE g_in = INVALID_HANDLE_VALUE;
static HWND g_label;
static FILE *g_log;

static int open_part(int n) {
  wchar_t p[MAX_PATH]; swprintf(p, MAX_PATH, L"%ls\\data-%d.bin", g_dir, n);
  if (g_in != INVALID_HANDLE_VALUE) CloseHandle(g_in);
  g_in = CreateFileW(p, GENERIC_READ, FILE_SHARE_READ, 0, OPEN_EXISTING, 0, 0);
  g_part = n;
  return g_in != INVALID_HANDLE_VALUE;
}

// Reads exactly n bytes from the parts, moving on to data-(N+1).bin at the end of each one.
static int rd(void *buf, DWORD n) {
  char *b = buf;
  while (n) {
    DWORD got = 0;
    if (!ReadFile(g_in, b, n, &got, 0)) return 0;
    if (got == 0) { if (!open_part(g_part + 1)) return 0; continue; }
    b += got; n -= got;
  }
  return 1;
}

static int rd_str(wchar_t *out, int cap) {
  DWORD len; char tmp[1024];
  if (!rd(&len, 4) || len >= sizeof(tmp) || !rd(tmp, len)) return 0;
  tmp[len] = 0;
  return MultiByteToWideChar(CP_UTF8, 0, tmp, -1, out, cap) > 0;
}

static void pump(const wchar_t *text) {
  MSG m;
  if (g_label && text) SetWindowTextW(g_label, text);
  while (PeekMessageW(&m, 0, 0, 0, PM_REMOVE)) { TranslateMessage(&m); DispatchMessageW(&m); }
}

static void shortcut(const wchar_t *lnk, const wchar_t *target, const wchar_t *workdir) {
  IShellLinkW *sl; IPersistFile *pf;
  if (FAILED(CoCreateInstance(&CLSID_ShellLink, 0, CLSCTX_INPROC_SERVER, &IID_IShellLinkW, (void **)&sl))) return;
  IShellLinkW_SetPath(sl, target);
  IShellLinkW_SetWorkingDirectory(sl, workdir);
  if (SUCCEEDED(IShellLinkW_QueryInterface(sl, &IID_IPersistFile, (void **)&pf))) {
    HRESULT hr = IPersistFile_Save(pf, lnk, TRUE);
    fprintf(g_log, "shortcut %ls -> 0x%08lx\n", lnk, (unsigned long)hr);
    IPersistFile_Release(pf);
  }
  IShellLinkW_Release(sl);
}

int WINAPI wWinMain(HINSTANCE hi, HINSTANCE prev, PWSTR cmdline, int show) {
  GetModuleFileNameW(0, g_dir, MAX_PATH);
  *wcsrchr(g_dir, L'\\') = 0;
  int silent = wcsstr(cmdline, L"/SILENT") || wcsstr(cmdline, L"/VERYSILENT");
  wchar_t game[256], mainexe[512], dest[MAX_PATH] = L"";
  const wchar_t *d = wcsstr(cmdline, L"/DIR=");
  if (d) {
    d += 5; int q = (*d == L'"'); if (q) d++;
    int i = 0; while (*d && i < MAX_PATH - 1 && (q ? *d != L'"' : *d != L' ')) dest[i++] = *d++;
    dest[i] = 0;
  }

  if (!open_part(1)) { MessageBoxW(0, L"data-1.bin is missing.", L"Setup", MB_ICONERROR); return 2; }
  char magic[4]; DWORD ver, count;
  if (!rd(magic, 4) || memcmp(magic, "MXPK", 4) || !rd(&ver, 4) || !rd_str(game, 256) || !rd_str(mainexe, 512) || !rd(&count, 4)) {
    MessageBoxW(0, L"The game data is damaged.", L"Setup", MB_ICONERROR); return 3;
  }
  if (!dest[0]) swprintf(dest, MAX_PATH, L"C:\\Games\\%ls", game);
  SHCreateDirectoryExW(0, dest, 0);
  wchar_t logp[MAX_PATH]; swprintf(logp, MAX_PATH, L"%ls\\install.log", dest);
  g_log = _wfopen(logp, L"w");
  fprintf(g_log, "installing %ls to %ls (%lu files)\n", game, dest, (unsigned long)count);

  if (!silent) {
    WNDCLASSW wc = {0}; wc.lpfnWndProc = DefWindowProcW; wc.hInstance = hi; wc.lpszClassName = L"mxsetup";
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1); RegisterClassW(&wc);
    wchar_t title[300]; swprintf(title, 300, L"Setup - %ls", game);
    HWND w = CreateWindowW(L"mxsetup", title, WS_OVERLAPPED | WS_CAPTION | WS_VISIBLE, 200, 200, 520, 140, 0, 0, hi, 0);
    g_label = CreateWindowW(L"STATIC", L"Preparing...", WS_CHILD | WS_VISIBLE, 16, 30, 480, 40, w, 0, hi, 0);
  }

  ULONGLONG total = 0;
  for (DWORD i = 0; i < count; i++) {
    wchar_t rel[512], path[MAX_PATH], msg[700]; unsigned long long size;
    if (!rd_str(rel, 512) || !rd(&size, 8)) { fprintf(g_log, "damaged at file %lu\n", (unsigned long)i); return 4; }
    swprintf(path, MAX_PATH, L"%ls\\%ls", dest, rel);
    wchar_t folder[MAX_PATH]; wcscpy(folder, path); *wcsrchr(folder, L'\\') = 0; SHCreateDirectoryExW(0, folder, 0);
    swprintf(msg, 700, L"Extracting %ls  (%lu of %lu, from data-%d.bin)", rel, (unsigned long)(i + 1), (unsigned long)count, g_part);
    pump(msg);
    HANDLE out = CreateFileW(path, GENERIC_WRITE, 0, 0, CREATE_ALWAYS, 0, 0);
    if (out == INVALID_HANDLE_VALUE) { fprintf(g_log, "cannot write %ls\n", path); return 5; }
    static char buf[1 << 20];
    while (size) {
      DWORD n = size > sizeof(buf) ? sizeof(buf) : (DWORD)size, w;
      if (!rd(buf, n)) { fprintf(g_log, "data ended early in %ls\n", rel); CloseHandle(out); return 6; }
      WriteFile(out, buf, n, &w, 0); size -= n; total += n;
    }
    CloseHandle(out);
    fprintf(g_log, "file %ls\n", rel);
  }

  pump(L"Creating shortcuts...");
  CoInitialize(0);
  wchar_t exe[MAX_PATH], exedir[MAX_PATH], folder[MAX_PATH], lnk[MAX_PATH];
  swprintf(exe, MAX_PATH, L"%ls\\%ls", dest, mainexe);
  wcscpy(exedir, exe); *wcsrchr(exedir, L'\\') = 0;
  if (SUCCEEDED(SHGetFolderPathW(0, CSIDL_COMMON_PROGRAMS, 0, 0, folder))) {
    wchar_t sub[MAX_PATH]; swprintf(sub, MAX_PATH, L"%ls\\%ls", folder, game); SHCreateDirectoryExW(0, sub, 0);
    swprintf(lnk, MAX_PATH, L"%ls\\%ls.lnk", sub, game); shortcut(lnk, exe, exedir);
  }
  if (SUCCEEDED(SHGetFolderPathW(0, CSIDL_DESKTOPDIRECTORY, 0, 0, folder))) {
    swprintf(lnk, MAX_PATH, L"%ls\\%ls.lnk", folder, game); shortcut(lnk, exe, exedir);
  }

  HKEY k; wchar_t key[400];
  swprintf(key, 400, L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\%ls_is1", game);
  if (RegCreateKeyExW(HKEY_LOCAL_MACHINE, key, 0, 0, 0, KEY_WRITE, 0, &k, 0) == ERROR_SUCCESS) {
    RegSetValueExW(k, L"DisplayName", 0, REG_SZ, (BYTE *)game, (DWORD)(wcslen(game) + 1) * 2);
    RegSetValueExW(k, L"InstallLocation", 0, REG_SZ, (BYTE *)dest, (DWORD)(wcslen(dest) + 1) * 2);
    RegSetValueExW(k, L"DisplayIcon", 0, REG_SZ, (BYTE *)exe, (DWORD)(wcslen(exe) + 1) * 2);
    RegCloseKey(k);
  }
  fprintf(g_log, "done, %llu MB\n", total >> 20);
  fclose(g_log);
  pump(L"Done.");
  Sleep(silent ? 0 : 800);
  return 0;
}
