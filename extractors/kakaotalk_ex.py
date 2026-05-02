import time
import win32con
import win32api
import win32gui
import ctypes
from pywinauto import clipboard

PBYTE256 = ctypes.c_ubyte * 256
_user32 = ctypes.WinDLL("user32")
GetKeyboardState = _user32.GetKeyboardState
SetKeyboardState = _user32.SetKeyboardState
PostMessage = win32api.PostMessage
SendMessage = win32gui.SendMessage
FindWindow = win32gui.FindWindow
IsWindow = win32gui.IsWindow
GetCurrentThreadId = win32api.GetCurrentThreadId
GetWindowThreadProcessId = _user32.GetWindowThreadProcessId
AttachThreadInput = _user32.AttachThreadInput
MapVirtualKeyA = _user32.MapVirtualKeyA
MapVirtualKeyW = _user32.MapVirtualKeyW
MakeLong = win32api.MAKELONG
w = win32con
# 조합키 쓰기 위해 by.Sol95
def PostKeyEx(hwnd, key, shift, specialkey):
if IsWindow(hwnd):
ThreadId = GetWindowThreadProcessId(hwnd, None)
lparam = MakeLong(0, MapVirtualKeyA(key, 0))
msg_down = w.WM_KEYDOWN
msg_up = w.WM_KEYUP
if specialkey:
lparam = lparam | 0x1000000
if len(shift) > 0:
pKeyBuffers = PBYTE256()
pKeyBuffers_old = PBYTE256()
SendMessage(hwnd, w.WM_ACTIVATE, w.WA_ACTIVE, 0)
AttachThreadInput(GetCurrentThreadId(), ThreadId,True)
GetKeyboardState(ctypes.byref(pKeyBuffers_old))
for modkey in shift:
if modkey == w.VK_MENU:
lparam = lparam | 0x20000000
msg_down = w.WM_SYSKEYDOWN
msg_up = w.WM_SYSKEYUP
pKeyBuffers[modkey] |= 128
SetKeyboardState(ctypes.byref(pKeyBuffers))
time.sleep(0.01)
PostMessage(hwnd, msg_down, key, lparam)
time.sleep(0.01)
PostMessage(hwnd, msg_up, key, lparam | 0xC0000000)
time.sleep(0.01)
SetKeyboardState(ctypes.byref(pKeyBuffers_old))
time.sleep(0.01)
AttachThreadInput(GetCurrentThreadId(), ThreadId,
False)
else:
SendMessage(hwnd, msg_down, key, lparam)
SendMessage(hwnd, msg_up, key, lparam | 0xC0000000)
def SendReturn(hwnd):
time.sleep(1)
win32api.PostMessage(hwnd, win32con.WM_KEYDOWN,
win32con.VK_RETURN, 0)
time.sleep(0.01)
win32api.PostMessage(hwnd, win32con.WM_KEYUP,
win32con.VK_RETURN, 0)
def open_chatroom(chatroom_name):
# # 채팅방 목록 검색하는 Edit (채팅방이 열려있지 않아도 전송
가능하게)
hwndkakao = win32gui.FindWindow(None, "카카오톡")
hwndkakao_edit1 = win32gui.FindWindowEx( hwndkakao, None,
"EVA_ChildWindow", None)
hwndkakao_edit2_1 = win32gui.FindWindowEx( hwndkakao_edit1,
None, "EVA_Window", None)
hwndkakao_edit2_2 = win32gui.FindWindowEx( hwndkakao_edit1,
hwndkakao_edit2_1, "EVA_Window", None)
hwndkakao_edit3 = win32gui.FindWindowEx( hwndkakao_edit2_2,
None, "Edit", None)
# # Edit에 검색 _ 입력되어있는 텍스트가 있어도 덮어쓰기됨
time.sleep(2)
win32api.SendMessage(hwndkakao_edit3, win32con.WM_SETTEXT,
0, chatroom_name)
time.sleep(2) # 안정성 위해 필요
SendReturn(hwndkakao_edit3)
time.sleep(2)
def main():
open_chatroom(kakao_opentalk_name)
time.sleep(2)
# # 핸들 _ 채팅방
hwndMain = win32gui.FindWindow( None, kakao_opentalk_name)
hwndListControl = win32gui.FindWindowEx(hwndMain, None,
"EVA_VH_ListControl_Dblclk", None)
# #조합키, 본문을 클립보드에 복사 ( ctl + A , C )
PostKeyEx(hwndListControl, ord('A'), [w.VK_CONTROL], False)
time.sleep(1)
PostKeyEx(hwndListControl, ord('C'), [w.VK_CONTROL], False)
ctext = clipboard.GetData()
print(ctext) # 내용 확인
main()
