#define COBJMACROS
#include <windows.h>
#include <d3d12.h>
#include <dxgi1_4.h>
#include <stdio.h>
#include <string.h>
static LRESULT CALLBACK wp(HWND h, UINT m, WPARAM w, LPARAM l){ if(m==WM_DESTROY){PostQuitMessage(0);return 0;} return DefWindowProcW(h,m,w,l); }
#define CHK(x) do{ hr=(x); fprintf(log,"%s -> 0x%08lx\n",#x,(unsigned long)hr); fflush(log); if(FAILED(hr)) { fclose(log); return 1; } }while(0)
int WINAPI wWinMain(HINSTANCE hi, HINSTANCE p, PWSTR a, int s){
  char lp[MAX_PATH]; GetModuleFileNameA(0,lp,MAX_PATH); strcpy(strrchr(lp,'\\')+1,"result.txt");
  FILE *log=fopen(lp,"w"); HRESULT hr;
  WNDCLASSW wc={0}; wc.lpfnWndProc=wp; wc.hInstance=hi; wc.lpszClassName=L"d3d12t"; RegisterClassW(&wc);
  HWND hw=CreateWindowW(L"d3d12t",L"MacX - DirectX 12 test",WS_OVERLAPPEDWINDOW|WS_VISIBLE,120,120,640,360,0,0,hi,0);
  IDXGIFactory4 *f=0; CHK(CreateDXGIFactory1(&IID_IDXGIFactory4,(void**)&f));
  IDXGIAdapter1 *ad=0; DXGI_ADAPTER_DESC1 desc;
  if(SUCCEEDED(IDXGIFactory4_EnumAdapters1(f,0,&ad)) && SUCCEEDED(IDXGIAdapter1_GetDesc1(ad,&desc)))
    fprintf(log,"adapter=%ls vram=%lluMB\n",desc.Description,(unsigned long long)(desc.DedicatedVideoMemory>>20));
  ID3D12Device *dev=0; CHK(D3D12CreateDevice((IUnknown*)ad,D3D_FEATURE_LEVEL_11_0,&IID_ID3D12Device,(void**)&dev));
  D3D12_COMMAND_QUEUE_DESC qd={0}; qd.Type=D3D12_COMMAND_LIST_TYPE_DIRECT;
  ID3D12CommandQueue *q=0; CHK(ID3D12Device_CreateCommandQueue(dev,&qd,&IID_ID3D12CommandQueue,(void**)&q));
  DXGI_SWAP_CHAIN_DESC1 sd={0}; sd.Width=640; sd.Height=360; sd.Format=DXGI_FORMAT_R8G8B8A8_UNORM; sd.SampleDesc.Count=1;
  sd.BufferUsage=DXGI_USAGE_RENDER_TARGET_OUTPUT; sd.BufferCount=2; sd.SwapEffect=DXGI_SWAP_EFFECT_FLIP_DISCARD;
  IDXGISwapChain1 *sc1=0; CHK(IDXGIFactory4_CreateSwapChainForHwnd(f,(IUnknown*)q,hw,&sd,0,0,&sc1));
  IDXGISwapChain3 *sc=0; CHK(IDXGISwapChain1_QueryInterface(sc1,&IID_IDXGISwapChain3,(void**)&sc));
  D3D12_DESCRIPTOR_HEAP_DESC hd={0}; hd.Type=D3D12_DESCRIPTOR_HEAP_TYPE_RTV; hd.NumDescriptors=2;
  ID3D12DescriptorHeap *heap=0; CHK(ID3D12Device_CreateDescriptorHeap(dev,&hd,&IID_ID3D12DescriptorHeap,(void**)&heap));
  UINT inc=ID3D12Device_GetDescriptorHandleIncrementSize(dev,D3D12_DESCRIPTOR_HEAP_TYPE_RTV);
  D3D12_CPU_DESCRIPTOR_HANDLE h0; heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(heap,&h0);
  ID3D12Resource *bb[2]; D3D12_CPU_DESCRIPTOR_HANDLE rtv[2];
  for(int i=0;i<2;i++){ CHK(IDXGISwapChain3_GetBuffer(sc,i,&IID_ID3D12Resource,(void**)&bb[i])); rtv[i].ptr=h0.ptr+i*inc; ID3D12Device_CreateRenderTargetView(dev,bb[i],0,rtv[i]); }
  ID3D12CommandAllocator *al=0; CHK(ID3D12Device_CreateCommandAllocator(dev,D3D12_COMMAND_LIST_TYPE_DIRECT,&IID_ID3D12CommandAllocator,(void**)&al));
  ID3D12GraphicsCommandList *cl=0; CHK(ID3D12Device_CreateCommandList(dev,0,D3D12_COMMAND_LIST_TYPE_DIRECT,al,0,&IID_ID3D12GraphicsCommandList,(void**)&cl));
  ID3D12GraphicsCommandList_Close(cl);
  ID3D12Fence *fe=0; CHK(ID3D12Device_CreateFence(dev,0,D3D12_FENCE_FLAG_NONE,&IID_ID3D12Fence,(void**)&fe));
  HANDLE ev=CreateEventW(0,FALSE,FALSE,0); UINT64 fv=0;
  float blue[4]={0.1f,0.3f,0.9f,1.0f}; DWORD t0=GetTickCount(); int frames=0; MSG msg;
  while(GetTickCount()-t0<8000){
    while(PeekMessageW(&msg,0,0,0,PM_REMOVE)){TranslateMessage(&msg);DispatchMessageW(&msg);}
    UINT i=IDXGISwapChain3_GetCurrentBackBufferIndex(sc);
    ID3D12CommandAllocator_Reset(al); ID3D12GraphicsCommandList_Reset(cl,al,0);
    D3D12_RESOURCE_BARRIER b={0}; b.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION; b.Transition.pResource=bb[i];
    b.Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES; b.Transition.StateBefore=D3D12_RESOURCE_STATE_PRESENT; b.Transition.StateAfter=D3D12_RESOURCE_STATE_RENDER_TARGET;
    ID3D12GraphicsCommandList_ResourceBarrier(cl,1,&b);
    ID3D12GraphicsCommandList_ClearRenderTargetView(cl,rtv[i],blue,0,0);
    b.Transition.StateBefore=D3D12_RESOURCE_STATE_RENDER_TARGET; b.Transition.StateAfter=D3D12_RESOURCE_STATE_PRESENT;
    ID3D12GraphicsCommandList_ResourceBarrier(cl,1,&b);
    ID3D12GraphicsCommandList_Close(cl);
    ID3D12CommandQueue_ExecuteCommandLists(q,1,(ID3D12CommandList**)&cl);
    IDXGISwapChain3_Present(sc,0,0);
    ID3D12CommandQueue_Signal(q,fe,++fv);
    if(ID3D12Fence_GetCompletedValue(fe)<fv){ ID3D12Fence_SetEventOnCompletion(fe,fv,ev); WaitForSingleObject(ev,2000); }
    frames++;
  }
  fprintf(log,"frames=%d fps=%.1f\n",frames,frames/8.0); fclose(log); return 0;
}
