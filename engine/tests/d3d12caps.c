// d3d12caps: what a D3D12 implementation offers (interfaces, feature options, shader model, SDK exports)
#define COBJMACROS
#include <windows.h>
#include <d3d12.h>
#include <dxgi1_6.h>
#include <stdio.h>
static FILE *o;
#define P(...) fprintf(o, __VA_ARGS__)
int WINAPI wWinMain(HINSTANCE hi, HINSTANCE p, PWSTR a, int s){
  char lp[MAX_PATH]; GetModuleFileNameA(0,lp,MAX_PATH); strcpy(strrchr(lp,'\\')+1,"caps.txt"); o=fopen(lp,"w");
  HMODULE m=GetModuleHandleA("d3d12.dll"); if(!m) m=LoadLibraryA("d3d12.dll");
  const char *ex[]={"D3D12CreateDevice","D3D12GetInterface","D3D12SerializeVersionedRootSignature","D3D12EnableExperimentalFeatures",0};
  for(int i=0;ex[i];i++) P("export %-38s %s\n", ex[i], GetProcAddress(m,ex[i])?"yes":"MISSING");
  IDXGIFactory6 *f6=0; IDXGIFactory1 *f1=0; CreateDXGIFactory1(&IID_IDXGIFactory1,(void**)&f1);
  P("IDXGIFactory6: %s\n", SUCCEEDED(IDXGIFactory1_QueryInterface(f1,&IID_IDXGIFactory6,(void**)&f6))?"yes":"no");
  IDXGIAdapter1 *ad=0; IDXGIFactory1_EnumAdapters1(f1,0,&ad); DXGI_ADAPTER_DESC1 d; IDXGIAdapter1_GetDesc1(ad,&d);
  P("adapter %ls vendor=%04x device=%04x\n", d.Description, d.VendorId, d.DeviceId);
  IDXGIAdapter4 *a4=0; P("IDXGIAdapter4: %s\n", SUCCEEDED(IDXGIAdapter1_QueryInterface(ad,&IID_IDXGIAdapter4,(void**)&a4))?"yes":"no");
  ID3D12Device *dev=0; HRESULT hr=D3D12CreateDevice((IUnknown*)ad,D3D_FEATURE_LEVEL_12_0,&IID_ID3D12Device,(void**)&dev);
  P("D3D12CreateDevice FL12_0 -> %08lx\n",(unsigned long)hr); if(FAILED(hr)){fclose(o);return 1;}
  const IID *ids[]={&IID_ID3D12Device1,&IID_ID3D12Device2,&IID_ID3D12Device3,&IID_ID3D12Device4,&IID_ID3D12Device5,
    &IID_ID3D12Device6,&IID_ID3D12Device7,&IID_ID3D12Device8,&IID_ID3D12Device9,&IID_ID3D12Device10};
  for(int i=0;i<10;i++){ void *x=0; P("ID3D12Device%d: %s\n", i+1, SUCCEEDED(ID3D12Device_QueryInterface(dev,ids[i],&x))?"yes":"no"); }
  D3D12_FEATURE_DATA_SHADER_MODEL sm={D3D_SHADER_MODEL_6_7}; hr=ID3D12Device_CheckFeatureSupport(dev,D3D12_FEATURE_SHADER_MODEL,&sm,sizeof sm);
  P("shader model: %08lx highest=0x%x\n",(unsigned long)hr,sm.HighestShaderModel);
  D3D12_FEATURE_DATA_ROOT_SIGNATURE rs={D3D_ROOT_SIGNATURE_VERSION_1_1}; hr=ID3D12Device_CheckFeatureSupport(dev,D3D12_FEATURE_ROOT_SIGNATURE,&rs,sizeof rs);
  P("root signature: %08lx v=0x%x\n",(unsigned long)hr,rs.HighestVersion);
  D3D_FEATURE_LEVEL fls[]={D3D_FEATURE_LEVEL_12_2,D3D_FEATURE_LEVEL_12_1,D3D_FEATURE_LEVEL_12_0}; D3D12_FEATURE_DATA_FEATURE_LEVELS fl={3,fls};
  hr=ID3D12Device_CheckFeatureSupport(dev,D3D12_FEATURE_FEATURE_LEVELS,&fl,sizeof fl); P("max feature level: %08lx 0x%x\n",(unsigned long)hr,fl.MaxSupportedFeatureLevel);
  D3D12_FEATURE_DATA_D3D12_OPTIONS o0={0}; hr=ID3D12Device_CheckFeatureSupport(dev,D3D12_FEATURE_D3D12_OPTIONS,&o0,sizeof o0);
  P("OPTIONS: %08lx binding tier=%d tiled=%d typedUAV=%d\n",(unsigned long)hr,o0.ResourceBindingTier,o0.TiledResourcesTier,o0.TypedUAVLoadAdditionalFormats);
  D3D12_FEATURE_DATA_D3D12_OPTIONS5 o5={0}; hr=ID3D12Device_CheckFeatureSupport(dev,D3D12_FEATURE_D3D12_OPTIONS5,&o5,sizeof o5);
  P("OPTIONS5: %08lx raytracing tier=0x%x\n",(unsigned long)hr,o5.RaytracingTier);
  D3D12_FEATURE_DATA_D3D12_OPTIONS7 o7={0}; hr=ID3D12Device_CheckFeatureSupport(dev,D3D12_FEATURE_D3D12_OPTIONS7,&o7,sizeof o7);
  P("OPTIONS7: %08lx mesh shader tier=0x%x\n",(unsigned long)hr,o7.MeshShaderTier);
  D3D12_FEATURE_DATA_D3D12_OPTIONS12 o12={0}; hr=ID3D12Device_CheckFeatureSupport(dev,D3D12_FEATURE_D3D12_OPTIONS12,&o12,sizeof o12);
  P("OPTIONS12: %08lx enhanced barriers=%d\n",(unsigned long)hr,o12.EnhancedBarriersSupported);
  for(int f=D3D12_FEATURE_D3D12_OPTIONS8; f<=D3D12_FEATURE_D3D12_OPTIONS18; f++){ char buf[256]={0}; hr=ID3D12Device_CheckFeatureSupport(dev,f,buf,sizeof buf); P("feature %d: %08lx\n",f,(unsigned long)hr); }
  fclose(o); return 0;
}
