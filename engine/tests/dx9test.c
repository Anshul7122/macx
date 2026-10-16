// DirectX 9 test "game": clears the window for 8 seconds and writes result.txt next to the .exe.
// Old games are mostly 32-bit DirectX 9, so this one is built as 32-bit.
#define COBJMACROS
#include <windows.h>
#include <d3d9.h>
#include <stdio.h>
#include <string.h>
static LRESULT CALLBACK wp(HWND h, UINT m, WPARAM w, LPARAM l){ if(m==WM_DESTROY){PostQuitMessage(0);return 0;} return DefWindowProcW(h,m,w,l); }
int WINAPI wWinMain(HINSTANCE hi, HINSTANCE p, PWSTR a, int s){
  char lp[MAX_PATH]; GetModuleFileNameA(0,lp,MAX_PATH); strcpy(strrchr(lp,0x5c)+1,"result.txt"); FILE *log = fopen(lp,"w");
  WNDCLASSW wc={0}; wc.lpfnWndProc=wp; wc.hInstance=hi; wc.lpszClassName=L"d3d9t"; RegisterClassW(&wc);
  HWND hw=CreateWindowW(L"d3d9t",L"MacX - DirectX 9 test",WS_OVERLAPPEDWINDOW|WS_VISIBLE,120,120,640,360,0,0,hi,0);
  IDirect3D9 *d3d=Direct3DCreate9(D3D_SDK_VERSION);
  fprintf(log,"Direct3DCreate9=%p bits=%d\n",(void*)d3d,(int)sizeof(void*)*8); fflush(log);
  if(!d3d){ fclose(log); return 1; }
  D3DADAPTER_IDENTIFIER9 id; if(SUCCEEDED(IDirect3D9_GetAdapterIdentifier(d3d,0,0,&id))) fprintf(log,"adapter=%s\n",id.Description);
  D3DPRESENT_PARAMETERS pp={0}; pp.Windowed=TRUE; pp.SwapEffect=D3DSWAPEFFECT_DISCARD; pp.BackBufferFormat=D3DFMT_UNKNOWN;
  pp.hDeviceWindow=hw; pp.PresentationInterval=D3DPRESENT_INTERVAL_IMMEDIATE;
  IDirect3DDevice9 *dev=0;
  HRESULT hr=IDirect3D9_CreateDevice(d3d,0,D3DDEVTYPE_HAL,hw,D3DCREATE_HARDWARE_VERTEXPROCESSING,&pp,&dev);
  fprintf(log,"create hr=0x%08lx\n",(unsigned long)hr); fflush(log);
  if(FAILED(hr)){ fclose(log); return 1; }
  DWORD t0=GetTickCount(); int frames=0; MSG msg;
  while(GetTickCount()-t0<8000){
    while(PeekMessageW(&msg,0,0,0,PM_REMOVE)){TranslateMessage(&msg);DispatchMessageW(&msg);}
    IDirect3DDevice9_Clear(dev,0,0,D3DCLEAR_TARGET,D3DCOLOR_XRGB(220,120,20),1.0f,0);
    IDirect3DDevice9_BeginScene(dev); IDirect3DDevice9_EndScene(dev);
    IDirect3DDevice9_Present(dev,0,0,0,0); frames++;
  }
  fprintf(log,"frames=%d fps=%.1f\n",frames,frames/8.0); fclose(log); return 0;
}
