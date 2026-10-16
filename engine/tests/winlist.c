#include <windows.h>
#include <stdio.h>
static BOOL CALLBACK cb(HWND h, LPARAM l){
  wchar_t t[256]={0}, c[128]={0}; RECT r; DWORD pid=0;
  GetWindowTextW(h,t,256); GetClassNameW(h,c,128); GetWindowRect(h,&r); GetWindowThreadProcessId(h,&pid);
  if(!t[0] && !IsWindowVisible(h)) return TRUE;
  wprintf(L"%p pid=%04lx vis=%d min=%d (%ld,%ld)-(%ld,%ld) class=%ls title=%ls\n", h, pid, IsWindowVisible(h), IsIconic(h), r.left,r.top,r.right,r.bottom,c,t);
  return TRUE;
}
int main(void){ EnumWindows(cb,0); return 0; }
