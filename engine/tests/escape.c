// escape test: tries to write outside its MacX box; argument = the Mac home folder (e.g. /Users/name)
#include <windows.h>
#include <stdio.h>
static const char *try_write(const wchar_t *path){
  HANDLE h=CreateFileW(path,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
  if(h==INVALID_HANDLE_VALUE){ static char b[32]; sprintf(b,"blocked (err %lu)",GetLastError()); return b; }
  DWORD n; WriteFile(h,"x",1,&n,NULL); CloseHandle(h); return "WRITTEN"; }
static const char *try_read(const wchar_t *path){
  HANDLE h=CreateFileW(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,0,NULL);
  if(h==INVALID_HANDLE_VALUE){ static char b[32]; sprintf(b,"blocked (err %lu)",GetLastError()); return b; }
  CloseHandle(h); return "READABLE"; }
int WINAPI wWinMain(HINSTANCE hi, HINSTANCE p, PWSTR a, int s){
  wchar_t home[MAX_PATH]; lstrcpynW(home,a,MAX_PATH); if(home[0]==L'"'){ lstrcpynW(home,a+1,MAX_PATH); home[lstrlenW(home)-1]=0; }
  for(wchar_t *c=home;*c;c++) if(*c==L'/') *c=L'\\';
  char lp[MAX_PATH]; GetModuleFileNameA(0,lp,MAX_PATH); strcpy(strrchr(lp,'\\')+1,"escape.txt"); FILE *o=fopen(lp,"w");
  wchar_t path[1024];
  swprintf(path,1024,L"Z:%ls\\macx_escape_z.txt",home);            fprintf(o,"write via Z: drive      : %s\n",try_write(path));
  swprintf(path,1024,L"\\\\?\\unix%ls\\macx_escape_unix.txt",home); fprintf(o,"write via \\\\?\\unix path : %s\n",try_write(path));
  swprintf(path,1024,L"\\\\?\\unix%ls\\.zshrc",home);              fprintf(o,"read ~/.zshrc           : %s\n",try_read(path));
  wchar_t prof[MAX_PATH]; GetEnvironmentVariableW(L"USERPROFILE",prof,MAX_PATH);
  swprintf(path,1024,L"%ls\\Desktop\\macx_desktop.txt",prof);       fprintf(o,"write Windows Desktop   : %s\n",try_write(path));
  swprintf(path,1024,L"%ls\\Documents\\macx_docs.txt",prof);        fprintf(o,"write Windows Documents : %s\n",try_write(path));
  swprintf(path,1024,L"W:\\inside_box.txt");                         fprintf(o,"write box folder (W:)   : %s\n",try_write(path));
  swprintf(path,1024,L"C:\\Program Files\\macx_installed.txt");      fprintf(o,"write C:\\Program Files : %s\n",try_write(path));
  DWORD drives=GetLogicalDrives(); fprintf(o,"drives:"); for(int i=0;i<26;i++) if(drives&(1<<i)) fprintf(o," %c:",'A'+i); fprintf(o,"\n");
  fclose(o); return 0; }
