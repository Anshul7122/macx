/* ntdlx.dll: lets Apple's D3DMetal DLLs (built for CrossOver / Wine 7.7) run on upstream Wine 11.
 * They import __wine_unix_call and NtQueryVirtualMemory from ntdll; upstream Wine 11 replaced
 * __wine_unix_call with the __wine_unix_call_dispatcher pointer. Their import tables are patched
 * to name this DLL instead of ntdll.dll; it forwards both calls. */
#include <windows.h>
#include <winternl.h>

typedef NTSTATUS (WINAPI *dispatcher_t)(UINT64 handle, unsigned int code, void *args);
typedef NTSTATUS (WINAPI *nqvm_t)(HANDLE, PVOID, int, PVOID, SIZE_T, SIZE_T *);

static dispatcher_t *dispatcher;
static nqvm_t nqvm;

static void init(void)
{
    HMODULE ntdll = GetModuleHandleW(L"ntdll.dll");
    dispatcher = (dispatcher_t *)GetProcAddress(ntdll, "__wine_unix_call_dispatcher");
    nqvm = (nqvm_t)GetProcAddress(ntdll, "NtQueryVirtualMemory");
}

__declspec(dllexport) NTSTATUS WINAPI __wine_unix_call(UINT64 handle, unsigned int code, void *args)
{
    if (!dispatcher) init();
    return (*dispatcher)(handle, code, args);
}

__declspec(dllexport) NTSTATUS WINAPI NtQueryVirtualMemory(HANDLE process, PVOID addr, int cls, PVOID info,
                                                           SIZE_T len, SIZE_T *res)
{
    if (!nqvm) init();
    return nqvm(process, addr, cls, info, len, res);
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved)
{
    if (reason == DLL_PROCESS_ATTACH) { DisableThreadLibraryCalls(inst); init(); }
    return TRUE;
}
