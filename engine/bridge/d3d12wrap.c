/* d3d12.dll wrapper for D3DMetal on Wine 11 (MacX). Apple's D3DMetal d3d12.dll is renamed d3dmt.dll;
 * most exports forward to it. This wrapper adds what DirectX 12 Agility SDK titles (GTA V Enhanced) need:
 *  - D3D12GetInterface (ID3D12SDKConfiguration / ID3D12DeviceFactory), missing from D3DMetal;
 *  - d3d12core.dll resident in the process, as on Windows (the game checks; Wine's placeholder suffices);
 *  - ID3D12CommandQueue::ExecuteCommandLists / Signal reachable through Windows executable memory. D3DMetal's
 *    methods are native Mach-O code that VirtualQuery reports as MEM_FREE, so overlay hook validation
 *    (Rockstar Social Club) fails and the game tears down its renderer, stalling at "Initializing". The shared
 *    queue vtable is pointed at forwarding thunks here (a small Wine unix call does the read-only write). */
#define COBJMACROS
#define INITGUID
#include <windows.h>
#include <d3d12.h>

DEFINE_GUID(CLSID_D3D12DeviceFactory_wp, 0x114863bf, 0xc386, 0x4aee, 0xb3, 0x9d, 0x8f, 0x0b, 0xbb, 0x06, 0x29, 0x55);

typedef HRESULT (WINAPI *create_device_t)(IUnknown *, D3D_FEATURE_LEVEL, REFIID, void **);
typedef NTSTATUS (WINAPI *unix_dispatcher_t)(UINT64, unsigned int, void *);
typedef NTSTATUS (WINAPI *nqvm_t)(HANDLE, PVOID, int, PVOID, SIZE_T, SIZE_T *);
typedef void (STDMETHODCALLTYPE *ecl_t)(ID3D12CommandQueue *, UINT, ID3D12CommandList *const *);
typedef HRESULT (STDMETHODCALLTYPE *signal_t)(ID3D12CommandQueue *, ID3D12Fence *, UINT64);
typedef HRESULT (WINAPI *enable_exp_t)(UINT, const IID *, void *, UINT *);
static HMODULE real;
static create_device_t real_create_device;
static enable_exp_t real_enable_exp;

static HINSTANCE self;
static UINT64 unix_handle;
static unix_dispatcher_t *unix_dispatcher;

struct write_ptr_params { void **slot; void *value; };

static BOOL write_ptr(void **slot, void *value)
{
    struct write_ptr_params p = { slot, value };
    if (!unix_handle)
    {
        HMODULE ntdll = GetModuleHandleW(L"ntdll.dll");
        nqvm_t nqvm = (nqvm_t)GetProcAddress(ntdll, "NtQueryVirtualMemory");
        unix_dispatcher = (unix_dispatcher_t *)GetProcAddress(ntdll, "__wine_unix_call_dispatcher");
        if (!nqvm || !unix_dispatcher || nqvm(GetCurrentProcess(), self, 1000 /* MemoryWineUnixFuncs */,
                                               &unix_handle, sizeof(unix_handle), NULL)) return FALSE;
    }
    return !(*unix_dispatcher)(unix_handle, 0, &p);
}

/* one entry per distinct D3DMetal queue vtable (direct / compute / copy may share one) */
static struct { void **vtbl; ecl_t ecl; signal_t signal; } queues[4];
static CRITICAL_SECTION queue_cs;

static void *find_orig(ID3D12CommandQueue *q, int which)
{
    for (int i = 0; i < 4; i++)
        if (queues[i].vtbl == (void **)q->lpVtbl) return which ? (void *)queues[i].signal : (void *)queues[i].ecl;
    return NULL;
}

static void STDMETHODCALLTYPE thunk_ExecuteCommandLists(ID3D12CommandQueue *q, UINT n, ID3D12CommandList *const *lists)
{
    ((ecl_t)find_orig(q, 0))(q, n, lists);
}

static HRESULT STDMETHODCALLTYPE thunk_Signal(ID3D12CommandQueue *q, ID3D12Fence *fence, UINT64 value)
{
    return ((signal_t)find_orig(q, 1))(q, fence, value);
}

static void patch_queue_vtable(ID3D12CommandQueue *q)
{
    void **vtbl = (void **)q->lpVtbl;
    int i;
    EnterCriticalSection(&queue_cs);
    for (i = 0; i < 4 && queues[i].vtbl; i++) if (queues[i].vtbl == vtbl) goto done;
    if (i == 4) goto done;
    queues[i].ecl = (ecl_t)vtbl[10];
    queues[i].signal = (signal_t)vtbl[14];
    queues[i].vtbl = vtbl;
    if (!write_ptr(&vtbl[10], (void *)thunk_ExecuteCommandLists) || !write_ptr(&vtbl[14], (void *)thunk_Signal))
        queues[i].vtbl = NULL;
done:
    LeaveCriticalSection(&queue_cs);
}

static void patch_device_queues(IUnknown *obj)
{
    static const D3D12_COMMAND_LIST_TYPE types[] = { D3D12_COMMAND_LIST_TYPE_DIRECT, D3D12_COMMAND_LIST_TYPE_COMPUTE,
                                                    D3D12_COMMAND_LIST_TYPE_COPY };
    ID3D12Device *dev;
    if (!obj || FAILED(IUnknown_QueryInterface(obj, &IID_ID3D12Device, (void **)&dev))) return;
    for (int t = 0; t < 3; t++)
    {
        D3D12_COMMAND_QUEUE_DESC desc = { types[t] };
        ID3D12CommandQueue *q;
        if (SUCCEEDED(ID3D12Device_CreateCommandQueue(dev, &desc, &IID_ID3D12CommandQueue, (void **)&q)))
        {
            patch_queue_vtable(q);
            ID3D12CommandQueue_Release(q);
        }
    }
    ID3D12Device_Release(dev);
}

static void load_real(void)
{
    if (real) return;
    real = LoadLibraryA("d3dmt.dll");
    real_create_device = (create_device_t)GetProcAddress(real, "D3D12CreateDevice");
    real_enable_exp = (enable_exp_t)GetProcAddress(real, "D3D12EnableExperimentalFeatures");
}

/* ---- ID3D12DeviceFactory ---- */
typedef struct { ID3D12DeviceFactory iface; LONG ref; D3D12_DEVICE_FACTORY_FLAGS flags; } factory;

static HRESULT WINAPI df_QueryInterface(ID3D12DeviceFactory *This, REFIID riid, void **out)
{
    if (IsEqualGUID(riid, &IID_IUnknown) || IsEqualGUID(riid, &IID_ID3D12DeviceFactory))
    { *out = This; ID3D12DeviceFactory_AddRef(This); return S_OK; }
    *out = NULL; return E_NOINTERFACE;
}
static ULONG WINAPI df_AddRef(ID3D12DeviceFactory *This) { return InterlockedIncrement(&((factory *)This)->ref); }
static ULONG WINAPI df_Release(ID3D12DeviceFactory *This)
{
    ULONG r = InterlockedDecrement(&((factory *)This)->ref);
    if (!r) HeapFree(GetProcessHeap(), 0, This);
    return r;
}
static HRESULT WINAPI df_InitializeFromGlobalState(ID3D12DeviceFactory *This) { return S_OK; }
static HRESULT WINAPI df_ApplyToGlobalState(ID3D12DeviceFactory *This) { return S_OK; }
static HRESULT WINAPI df_SetFlags(ID3D12DeviceFactory *This, D3D12_DEVICE_FACTORY_FLAGS f) { ((factory *)This)->flags = f; return S_OK; }
static D3D12_DEVICE_FACTORY_FLAGS WINAPI df_GetFlags(ID3D12DeviceFactory *This) { return ((factory *)This)->flags; }
static HRESULT WINAPI df_GetConfigurationInterface(ID3D12DeviceFactory *This, REFCLSID clsid, REFIID riid, void **out)
{ *out = NULL; return E_NOINTERFACE; }
static HRESULT WINAPI df_EnableExperimentalFeatures(ID3D12DeviceFactory *This, UINT n, const IID *ids, void *cfg, UINT *sizes)
{ load_real(); return real_enable_exp ? real_enable_exp(n, ids, cfg, sizes) : E_NOINTERFACE; }
__declspec(dllexport) HRESULT WINAPI D3D12CreateDevice(IUnknown *adapter, D3D_FEATURE_LEVEL fl, REFIID riid, void **out)
{
    HRESULT hr;
    load_real();
    if (!real_create_device) return E_FAIL;
    hr = real_create_device(adapter, fl, riid, out);
    if (SUCCEEDED(hr) && out && *out) patch_device_queues((IUnknown *)*out);
    return hr;
}

static HRESULT WINAPI df_CreateDevice(ID3D12DeviceFactory *This, IUnknown *adapter, D3D_FEATURE_LEVEL fl, REFIID riid, void **out)
{ return D3D12CreateDevice(adapter, fl, riid, out); }

static ID3D12DeviceFactoryVtbl df_vtbl = {
    df_QueryInterface, df_AddRef, df_Release, df_InitializeFromGlobalState, df_ApplyToGlobalState,
    df_SetFlags, df_GetFlags, df_GetConfigurationInterface, df_EnableExperimentalFeatures, df_CreateDevice };

static HRESULT new_factory(REFIID riid, void **out)
{
    factory *f = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(*f));
    HRESULT hr;
    if (!f) return E_OUTOFMEMORY;
    f->iface.lpVtbl = &df_vtbl; f->ref = 1;
    hr = df_QueryInterface(&f->iface, riid, out);
    df_Release(&f->iface);
    return hr;
}

/* ---- ID3D12SDKConfiguration1 (static singleton) ---- */
static HRESULT WINAPI sc_QueryInterface(ID3D12SDKConfiguration1 *This, REFIID riid, void **out)
{
    if (IsEqualGUID(riid, &IID_IUnknown) || IsEqualGUID(riid, &IID_ID3D12SDKConfiguration) ||
        IsEqualGUID(riid, &IID_ID3D12SDKConfiguration1)) { *out = This; return S_OK; }
    *out = NULL; return E_NOINTERFACE;
}
static ULONG WINAPI sc_AddRef(ID3D12SDKConfiguration1 *This) { return 2; }
static ULONG WINAPI sc_Release(ID3D12SDKConfiguration1 *This) { return 1; }
static HRESULT WINAPI sc_SetSDKVersion(ID3D12SDKConfiguration1 *This, UINT ver, LPCSTR path) { return S_OK; }
static HRESULT WINAPI sc_CreateDeviceFactory(ID3D12SDKConfiguration1 *This, UINT ver, LPCSTR path, REFIID riid, void **out)
{ return new_factory(riid, out); }
static void WINAPI sc_FreeUnusedSDKs(ID3D12SDKConfiguration1 *This) { }

static ID3D12SDKConfiguration1Vtbl sc_vtbl = {
    sc_QueryInterface, sc_AddRef, sc_Release, sc_SetSDKVersion, sc_CreateDeviceFactory, sc_FreeUnusedSDKs };
static ID3D12SDKConfiguration1 sdk_config = { &sc_vtbl };

__declspec(dllexport) HRESULT WINAPI D3D12GetInterface(REFCLSID clsid, REFIID riid, void **out)
{
    if (!out) return E_POINTER;
    *out = NULL;
    if (IsEqualGUID(clsid, &CLSID_D3D12SDKConfiguration)) return sc_QueryInterface(&sdk_config, riid, out);
    if (IsEqualGUID(clsid, &CLSID_D3D12DeviceFactory_wp)) return new_factory(riid, out);
    return E_NOINTERFACE;  /* Debug, Tools, DRED: not available */
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, void *reserved)
{
    if (reason == DLL_PROCESS_ATTACH)
    {
        self = inst;
        DisableThreadLibraryCalls(inst);
        InitializeCriticalSection(&queue_cs);
        LoadLibraryA("d3d12core.dll");  /* Agility SDK titles expect D3D12Core resident next to d3d12 */
    }
    return TRUE;
}
