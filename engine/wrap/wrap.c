// Generic CEF helper wrapper: <name>.exe launches <name>_real.exe from the same folder with the
// same arguments plus extra Chromium switches read from wrap_flags.txt (one line).
// Default extra switches if the file is missing: --in-process-gpu
#include <windows.h>
#include <wchar.h>

static const wchar_t *skip_argv0(const wchar_t *c) {
    if (*c == L'"') { c++; while (*c && *c != L'"') c++; if (*c) c++; }
    else { while (*c && *c != L' ' && *c != L'\t') c++; }
    return c;
}

int WINAPI wWinMain(HINSTANCE h, HINSTANCE p, PWSTR a, int s) {
    wchar_t self[MAX_PATH], real[MAX_PATH], cfg[MAX_PATH], extra[2048] = L" --in-process-gpu";
    GetModuleFileNameW(NULL, self, MAX_PATH);
    wcscpy(real, self);
    wchar_t *dot = wcsrchr(real, L'.'); if (dot) *dot = 0;
    wcscat(real, L"_real.exe");
    wcscpy(cfg, self);
    wchar_t *slash = wcsrchr(cfg, L'\\'); if (slash) slash[1] = 0;
    wcscat(cfg, L"wrap_flags.txt");
    HANDLE f = CreateFileW(cfg, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (f != INVALID_HANDLE_VALUE) {
        char buf[1024] = {0}; DWORD n = 0;
        ReadFile(f, buf, sizeof(buf) - 1, &n, NULL); CloseHandle(f);
        for (DWORD i = 0; i < n; i++) if (buf[i] == '\r' || buf[i] == '\n') { buf[i] = 0; break; }
        extra[0] = L' ';
        MultiByteToWideChar(CP_UTF8, 0, buf, -1, extra + 1, 2046);
    }
    const wchar_t *rest = skip_argv0(GetCommandLineW());
    size_t len = wcslen(real) + wcslen(rest) + wcslen(extra) + 8;
    wchar_t *cmd = (wchar_t *)HeapAlloc(GetProcessHeap(), 0, len * sizeof(wchar_t));
    wcscpy(cmd, L"\""); wcscat(cmd, real); wcscat(cmd, L"\""); wcscat(cmd, rest); wcscat(cmd, extra);
    STARTUPINFOW si; PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof si); si.cb = sizeof si; ZeroMemory(&pi, sizeof pi);
    if (!CreateProcessW(real, cmd, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi)) return 1;
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 0; GetExitCodeProcess(pi.hProcess, &code);
    return (int)code;
}
