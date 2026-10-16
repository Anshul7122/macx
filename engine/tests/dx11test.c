#define COBJMACROS
#include <windows.h>
#include <d3d11.h>
#include <dxgi.h>
#include <stdio.h>
#include <string.h>
static LRESULT CALLBACK wp(HWND h, UINT m, WPARAM w, LPARAM l){ if(m==WM_DESTROY){PostQuitMessage(0);return 0;} return DefWindowProcW(h,m,w,l); }
int WINAPI wWinMain(HINSTANCE hi, HINSTANCE p, PWSTR a, int s){
  char lp[MAX_PATH]; GetModuleFileNameA(0,lp,MAX_PATH); strcpy(strrchr(lp,0x5c)+1,"result.txt"); FILE *log = fopen(lp,"w");
  WNDCLASSW wc={0}; wc.lpfnWndProc=wp; wc.hInstance=hi; wc.lpszClassName=L"d3dt"; RegisterClassW(&wc);
  HWND hw=CreateWindowW(L"d3dt",L"MacX - DirectX 11 test",WS_OVERLAPPEDWINDOW|WS_VISIBLE,100,100,640,360,0,0,hi,0);
  DXGI_SWAP_CHAIN_DESC sd={0}; sd.BufferCount=2; sd.BufferDesc.Width=640; sd.BufferDesc.Height=360;
  sd.BufferDesc.Format=DXGI_FORMAT_R8G8B8A8_UNORM; sd.BufferUsage=DXGI_USAGE_RENDER_TARGET_OUTPUT; sd.OutputWindow=hw;
  sd.SampleDesc.Count=1; sd.Windowed=TRUE; sd.SwapEffect=DXGI_SWAP_EFFECT_FLIP_DISCARD;
  ID3D11Device *dev=0; ID3D11DeviceContext *ctx=0; IDXGISwapChain *sc=0; D3D_FEATURE_LEVEL fl=0;
  HRESULT hr=D3D11CreateDeviceAndSwapChain(0,D3D_DRIVER_TYPE_HARDWARE,0,0,0,0,D3D11_SDK_VERSION,&sd,&sc,&dev,&fl,&ctx);
  fprintf(log,"create hr=0x%08lx featurelevel=0x%x\n",(unsigned long)hr,(unsigned)fl); fflush(log);
  if(FAILED(hr)) { fclose(log); return 1; }
  IDXGIDevice *dd=0; IDXGIAdapter *ad=0; DXGI_ADAPTER_DESC desc;
  if(SUCCEEDED(ID3D11Device_QueryInterface(dev,&IID_IDXGIDevice,(void**)&dd)) && SUCCEEDED(IDXGIDevice_GetAdapter(dd,&ad)) && SUCCEEDED(IDXGIAdapter_GetDesc(ad,&desc)))
    fprintf(log,"adapter=%ls vram=%lluMB\n",desc.Description,(unsigned long long)(desc.DedicatedVideoMemory>>20));
  ID3D11Texture2D *bb=0; ID3D11RenderTargetView *rtv=0;
  IDXGISwapChain_GetBuffer(sc,0,&IID_ID3D11Texture2D,(void**)&bb); ID3D11Device_CreateRenderTargetView(dev,(ID3D11Resource*)bb,0,&rtv);
  float green[4]={0.0f,0.8f,0.2f,1.0f}; DWORD t0=GetTickCount(); int frames=0; MSG msg;
  while(GetTickCount()-t0<8000){
    while(PeekMessageW(&msg,0,0,0,PM_REMOVE)){TranslateMessage(&msg);DispatchMessageW(&msg);}
    ID3D11DeviceContext_OMSetRenderTargets(ctx,1,&rtv,0); ID3D11DeviceContext_ClearRenderTargetView(ctx,rtv,green);
    IDXGISwapChain_Present(sc,0,0); frames++;
  }
  fprintf(log,"frames=%d fps=%.1f\n",frames,frames/8.0); fclose(log); return 0;
}
