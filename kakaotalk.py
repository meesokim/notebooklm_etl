import sys
import time
import pathlib
import ctypes
import struct
import re
import os
import win32con
import win32api
import win32gui
import win32clipboard

PBYTE256 = ctypes.c_ubyte * 256
_user32 = ctypes.WinDLL("user32")
GetKeyboardState = _user32.GetKeyboardState
SetKeyboardState = _user32.SetKeyboardState
PostMessage = win32api.PostMessage
SendMessage = win32gui.SendMessage
FindWindow = win32gui.FindWindow
FindWindowEx = win32gui.FindWindowEx
IsWindow = win32gui.IsWindow
GetCurrentThreadId = win32api.GetCurrentThreadId
GetWindowThreadProcessId = _user32.GetWindowThreadProcessId
AttachThreadInput = _user32.AttachThreadInput
MapVirtualKeyA = _user32.MapVirtualKeyA
SendMessageW = _user32.SendMessageW
MakeLong = win32api.MAKELONG
w = win32con

from win32con import PAGE_READWRITE, MEM_COMMIT, PROCESS_ALL_ACCESS

VirtualAllocEx = ctypes.windll.kernel32.VirtualAllocEx
VirtualFreeEx = ctypes.windll.kernel32.VirtualFreeEx
OpenProcess = ctypes.windll.kernel32.OpenProcess
WriteProcessMemory = ctypes.windll.kernel32.WriteProcessMemory


def dragFileToWnd(file, hwnd):
    """Drag a file into a kakao chat window using WM_DROPFILES."""
    filepath = bytes(file + '\0', encoding="GBK")
    DropFilesInfo = struct.pack("iiiii" + str(len(filepath)) + "s", *[0x14, 0x0A, 0x0A, 0, 0, filepath])
    s_buff = ctypes.create_string_buffer(DropFilesInfo)

    pid = ctypes.c_uint(0)
    GetWindowThreadProcessId(hwnd, ctypes.addressof(pid))
    hProcHnd = OpenProcess(PROCESS_ALL_ACCESS, False, pid.value)
    pMem = VirtualAllocEx(hProcHnd, 0, len(DropFilesInfo), MEM_COMMIT, PAGE_READWRITE)

    copied = ctypes.c_int(0)
    WriteProcessMemory(hProcHnd, pMem, s_buff, len(DropFilesInfo), ctypes.addressof(copied))
    win32gui.SendMessage(hwnd, win32con.WM_DROPFILES, pMem, 0)
    VirtualFreeEx(hProcHnd, pMem, 0, win32con.MEM_RELEASE)


def _set_clipboard_text(text):
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def _get_clipboard_text():
    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT) or ""
    except Exception:
        return ""
    finally:
        win32clipboard.CloseClipboard()
    return ""


def _send_hotkey(hwnd, mod_vk, key_vk, pre_delay=0.05, gap=0.03):
    if hwnd and IsWindow(hwnd):
        try:
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
        except Exception:
            pass
    time.sleep(pre_delay)
    ku = win32con.KEYEVENTF_KEYUP
    win32api.keybd_event(mod_vk, 0, 0, 0)
    time.sleep(gap)
    win32api.keybd_event(key_vk, 0, 0, 0)
    time.sleep(gap)
    win32api.keybd_event(key_vk, 0, ku, 0)
    time.sleep(gap)
    win32api.keybd_event(mod_vk, 0, ku, 0)
    return True


def PostKeyEx(hwnd, key, shift, specialkey=False):
    if not IsWindow(hwnd):
        return False

    ThreadId = GetWindowThreadProcessId(hwnd, None)
    lparam = MakeLong(0, MapVirtualKeyA(key, 0))
    msg_down = w.WM_KEYDOWN
    msg_up = w.WM_KEYUP
    if specialkey:
        lparam |= 0x1000000

    if len(shift) > 0:
        pKeyBuffers = PBYTE256()
        pKeyBuffers_old = PBYTE256()
        SendMessage(hwnd, w.WM_ACTIVATE, w.WA_ACTIVE, 0)
        AttachThreadInput(GetCurrentThreadId(), ThreadId, True)
        GetKeyboardState(ctypes.byref(pKeyBuffers_old))

        for modkey in shift:
            if modkey in (w.VK_MENU, w.VK_LMENU, w.VK_RMENU):
                lparam |= 0x20000000
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
        AttachThreadInput(GetCurrentThreadId(), ThreadId, False)
    else:
        SendMessage(hwnd, msg_down, key, lparam)
        SendMessage(hwnd, msg_up, key, lparam | 0xC0000000)

    return True


def SendReturn(hwnd):
    time.sleep(0.1)
    win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
    time.sleep(0.01)
    win32api.PostMessage(hwnd, win32con.WM_KEYUP, win32con.VK_RETURN, 0)
    return True


def send_alt_s(hwnd):
    """Alt+S: 공통 저장 대화 상자(#32770)는 PostMessage로 보낸 WM_SYSKEY*를
    가속키로 처리하지 않는 경우가 많아, 실제 입력(keybd_event)으로 보낸다."""
    if not hwnd or not IsWindow(hwnd):
        return False
    try:
        win32gui.SetForegroundWindow(hwnd)
        win32gui.BringWindowToTop(hwnd)
    except Exception:
        pass
    time.sleep(0.15)
    return _send_hotkey(hwnd, win32con.VK_MENU, ord("S"), pre_delay=0.15, gap=0.04)


def press_return(hwnd=None):
    """전경 창(또는 지정 창)에 Enter를 보낸다."""
    if hwnd and IsWindow(hwnd):
        try:
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
            time.sleep(0.05)
        except Exception:
            pass
    vk = win32con.VK_RETURN
    ku = win32con.KEYEVENTF_KEYUP
    win32api.keybd_event(vk, 0, 0, 0)
    time.sleep(0.03)
    win32api.keybd_event(vk, 0, ku, 0)
    return True


def send_alt_f4(hwnd):
    """지정 창을 전경으로 올린 뒤 Alt+F4를 보낸다."""
    if not hwnd or not IsWindow(hwnd):
        return False
    try:
        win32gui.SetForegroundWindow(hwnd)
        win32gui.BringWindowToTop(hwnd)
    except Exception:
        pass
    time.sleep(0.1)
    return _send_hotkey(hwnd, win32con.VK_MENU, win32con.VK_F4, pre_delay=0.1, gap=0.03)


def close_chatroom_window(hwnd_chatroom, chatroom_name=""):
    """해당 채팅방 창만 닫는다. (WM_CLOSE 우선, 실패 시 Alt+F4 폴백)"""
    target = hwnd_chatroom
    if (not target or not IsWindow(target)) and chatroom_name:
        target = FindWindow(None, chatroom_name)
    if not target or not IsWindow(target):
        return False
    try:
        PostMessage(int(target), win32con.WM_CLOSE, 0, 0)
        return True
    except Exception:
        return send_alt_f4(target)


def ensure_txt_filepath(filepath):
    """확장자가 없으면 .txt를 붙인다."""
    if not filepath:
        return filepath
    p = pathlib.PureWindowsPath(filepath)
    if p.suffix:
        return str(p)
    return str(p.with_suffix(".txt"))


def read_saved_text_file(filepath, retries=10, pause=0.2):
    """저장된 텍스트 파일 내용을 읽는다. (인코딩 폴백 포함)"""
    if not filepath:
        return ""
    for _ in range(max(1, retries)):
        if pathlib.Path(filepath).exists():
            break
        time.sleep(pause)
    if not pathlib.Path(filepath).exists():
        return ""

    encodings = ("utf-8-sig", "cp949", "utf-16", "utf-8")
    for enc in encodings:
        try:
            with open(filepath, "r", encoding=enc) as f:
                return f.read()
        except Exception:
            continue
    return ""


def _safe_filename_part(text):
    """파일명에 안전한 문자열로 정리."""
    if not text:
        return "chatroom"
    s = str(text).strip()
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s)
    s = re.sub(r"\s+", "_", s)
    s = s.strip(" ._")
    return s or "chatroom"


def rename_saved_file_with_chatroom(filepath, chatroom):
    """파일명을 `대화명_원본파일명`으로 변경하고 새 경로를 반환."""
    if not filepath:
        return filepath
    src = pathlib.Path(filepath)
    if not src.exists():
        return filepath

    prefix = _safe_filename_part(chatroom)
    base_name = src.stem
    ext = src.suffix
    target = src.with_name(f"{prefix}_{base_name}{ext}")

    if target == src:
        return str(src)

    idx = 1
    while target.exists():
        target = src.with_name(f"{prefix}_{base_name}_{idx}{ext}")
        idx += 1

    try:
        src.rename(target)
        return str(target)
    except Exception:
        return str(src)


def find_save_dialog(timeout=10):
    """Find a file save dialog window by class and title. More robustly."""
    end_time = time.time() + timeout

    def enum_windows_proc(hwnd, lParam):
        class_name = win32gui.GetClassName(hwnd)
        title = win32gui.GetWindowText(hwnd) or ""
        if class_name == "#32770" and any(k in title for k in ["저장", "다른 이름으로 저장", "Save", "Save As"]):
            if win32gui.IsWindowVisible(hwnd):
                lParam.append(hwnd)
        return True

    while time.time() < end_time:
        dialogs = []
        win32gui.EnumWindows(enum_windows_proc, dialogs)
        if dialogs:
            return dialogs[0]
        time.sleep(0.2)
    return None


def wait_until_window_closed(hwnd, timeout=5):
    end_time = time.time() + timeout
    while time.time() < end_time:
        if not hwnd or not IsWindow(hwnd):
            return True
        time.sleep(0.05)
    return False


def find_foreground_dialog(timeout=2):
    """전경에 뜬 일반 다이얼로그(#32770)를 찾는다."""
    end_time = time.time() + timeout
    while time.time() < end_time:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd and IsWindow(hwnd):
            root = win32gui.GetAncestor(hwnd, win32con.GA_ROOT)
            if root and IsWindow(root):
                try:
                    if win32gui.GetClassName(root) == "#32770":
                        return root
                except Exception:
                    pass
        time.sleep(0.05)
    return None


def confirm_after_save(prev_save_dialog, timeout=3):
    """저장 후 뜨는 확인 팝업을 Enter로 수락한다."""
    # 1) 저장 창이 닫힐 때까지 먼저 대기
    wait_until_window_closed(prev_save_dialog, timeout=2.5)
    # 2) 뒤이어 뜨는 확인 팝업(덮어쓰기 등) 처리
    hwnd_confirm = find_foreground_dialog(timeout=timeout)
    if hwnd_confirm:
        press_return(hwnd_confirm)
        return True
    # 팝업이 없으면 조용히 통과
    return False


def _iter_child_windows(hwnd_parent):
    children = []
    win32gui.EnumChildWindows(hwnd_parent, lambda h, _: children.append(h), None)
    return children


def _get_dlg_ctrl_id(hwnd):
    return ctypes.windll.user32.GetDlgCtrlID(int(hwnd))


def _read_unicode_wnd_text(hwnd):
    """GetWindowText / WM_GETTEXTW — 콤보박스·에디트 전용 문자열 버퍼로 읽는다."""
    if not hwnd or not IsWindow(hwnd):
        return ""
    h = int(hwnd)
    gw = (win32gui.GetWindowText(hwnd) or "").strip()
    try:
        n = int(SendMessageW(h, win32con.WM_GETTEXTLENGTH, 0, 0))
        if n < 0 or n > 65535:
            n = 0
    except Exception:
        n = 0
    if n <= 0:
        return gw
    buf = ctypes.create_unicode_buffer(n + 1)
    try:
        SendMessageW(h, win32con.WM_GETTEXT, n + 1, ctypes.byref(buf))
    except Exception:
        return gw
    wm = buf.value.strip()
    return wm or gw


def _descendants_dfs(hwnd_parent):
    for ch in _iter_child_windows(hwnd_parent):
        yield ch
        yield from _descendants_dfs(ch)


def _wnd_bottom(hwnd):
    try:
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        return int(b)
    except Exception:
        return -1


# 구형 파일 대화 상자: 파일 이름 콤보/에디트(및 변형 리소스) ID 후보 (dlgs 리소스/문헌 참고).
_FILENAME_CTRL_IDS = (0x047C, 0x0480)  # 1148 파일명 콤보, 1152 구 리소스 edt1 등


def _find_hwnd_by_dlg_ctrl_id(hwnd_root, target_id):
    for h in _descendants_dfs(hwnd_root):
        if _get_dlg_ctrl_id(h) == target_id:
            return h
    return None


def _combo_inner_edit(hwnd_combo):
    try:
        if not hwnd_combo or not IsWindow(hwnd_combo):
            return None
        return FindWindowEx(int(hwnd_combo), None, "Edit", None)
    except Exception:
        return None


def _inner_edit_comboex(hwnd_cbex):
    try:
        if not hwnd_cbex or not IsWindow(hwnd_cbex):
            return None
        hwnd_cbex = int(hwnd_cbex)
    except Exception:
        return None

    try:
        inner_cb = FindWindowEx(hwnd_cbex, None, "ComboBox", None)
    except Exception:
        inner_cb = None
    if inner_cb:
        try:
            nested = FindWindowEx(int(inner_cb), None, "Edit", None)
        except Exception:
            nested = None
        if nested:
            return nested
    try:
        return FindWindowEx(hwnd_cbex, None, "Edit", None)
    except Exception:
        return None


def _pick_lowest_candidate_text(candidates_hwnd):
    """주소표시줄·검색용 Edit 위에 선택된 파일명이 오는 레이아웃이 많아, 화면 하단(y 큰)부터 고른다."""
    # WM_GETTEXT로 유효한 문자열인 컨트롤만 후보로
    texts = [(h, _read_unicode_wnd_text(h)) for h in candidates_hwnd]
    nonempty = [(h, t) for h, t in texts if (t or "").strip()]
    if not nonempty:
        return ""

    bottom_y = max(_wnd_bottom(h) for h, _ in nonempty)

    # 하단 줄에 붙어 있는 컨트롤 우선 (같은 대략 줄이면 문자열 더 긴 쪽).
    near_bottom = [(h, t) for h, t in nonempty if bottom_y - _wnd_bottom(h) <= 80]
    pool = near_bottom if near_bottom else nonempty

    pool.sort(key=lambda ht: (-_wnd_bottom(ht[0]), -len(ht[1])))
    best_text = pool[0][1].strip()
    return best_text


def get_save_dialog_filename(hwnd_dialog, retries=25, pause=0.08):
    """저장(#32770) 대화 상자에서 기본 저장 파일명을 읽는다.

    카카오/탐색기 스타일 대화 상자에서는 파일명이 최상위 Edit가 아니라
    ComboBoxEx32/ComboBox 내부 Edit에 있으며, 초기 렌더 직후엔 빈 상태일 수 있어
    짧게 재시도한다.
    """
    if not hwnd_dialog or not IsWindow(hwnd_dialog):
        return ""

    cls_pref = frozenset(("Edit", "ComboBox", "ComboBoxEx32", "RichEdit20W", "RichEdit50W"))

    try:
        win32gui.SetForegroundWindow(hwnd_dialog)
        win32gui.BringWindowToTop(hwnd_dialog)
        time.sleep(0.05)
    except Exception:
        pass

    # 단일 문자열 검사 헬퍼
    def read_from_known_ids(root):
        for cid in _FILENAME_CTRL_IDS:
            h = _find_hwnd_by_dlg_ctrl_id(root, cid)
            if not h:
                continue
            t = _read_unicode_wnd_text(h)
            if not t.strip():
                inner_cb = FindWindowEx(h, None, "ComboBox", None)
                if inner_cb:
                    t = _read_unicode_wnd_text(inner_cb)
            if not t.strip():
                for maybe in (FindWindowEx(h, None, "Edit", None), _combo_inner_edit(h)):
                    if maybe and IsWindow(maybe):
                        t = _read_unicode_wnd_text(maybe)
                        if t.strip():
                            break
            if t.strip():
                return t.strip()
        return ""

    for _attempt in range(max(1, retries)):
        if not IsWindow(hwnd_dialog):
            break

        t = read_from_known_ids(hwnd_dialog)
        if t:
            return t

        hwnd_list = []
        seen = set()

        def _addhwnd(x):
            if not x or not IsWindow(x):
                return
            k = int(x)
            if k in seen:
                return
            seen.add(k)
            hwnd_list.append(x)

        descendants = list(_descendants_dfs(hwnd_dialog))
        # ComboBoxEx32 내부 Edit → 일반 ComboBox 자식 Edit → 기타 에디터류
        for h in descendants:
            try:
                cn = win32gui.GetClassName(h)
            except Exception:
                continue
            if cn == "ComboBoxEx32":
                inner_edit = _inner_edit_comboex(h)
                if inner_edit:
                    _addhwnd(inner_edit)
        for h in descendants:
            try:
                cn = win32gui.GetClassName(h)
            except Exception:
                continue
            if cn == "ComboBox":
                ne = FindWindowEx(h, None, "Edit", None)
                if ne:
                    _addhwnd(ne)
        for h in descendants:
            try:
                cn = win32gui.GetClassName(h)
            except Exception:
                continue
            if cn in cls_pref and cn != "ComboBox":
                _addhwnd(h)

        picked = _pick_lowest_candidate_text(hwnd_list)
        if picked:
            return picked

        time.sleep(pause)

    return ""


_WIN_PATH_RE = re.compile(r"^(?:[A-Za-z]:\\|\\\\).+")
_WM_USER = 0x0400
_CDM_FIRST = _WM_USER + 100
_CDM_GETFILEPATH = _CDM_FIRST + 1
_CDM_GETFOLDERPATH = _CDM_FIRST + 2


def _get_dialog_text_by_cdm(hwnd_dialog, msg, max_chars=2048):
    """공용 파일 대화상자 메시지(CDM_*)로 경로 문자열을 얻는다."""
    if not hwnd_dialog or not IsWindow(hwnd_dialog):
        return ""
    buf = ctypes.create_unicode_buffer(max_chars)
    try:
        n = int(SendMessageW(int(hwnd_dialog), msg, max_chars, ctypes.byref(buf)))
    except Exception:
        return ""
    if n <= 0:
        return ""
    text = buf.value.strip()
    return text


def get_save_dialog_filepath(hwnd_dialog):
    """저장 대화상자에서 full path를 직접 조회한다."""
    return _get_dialog_text_by_cdm(hwnd_dialog, _CDM_GETFILEPATH)


def _get_save_dialog_directory_by_addressbar(hwnd_dialog):
    """저장창 주소창(Alt+D) 값을 클립보드로 읽어 디렉토리 경로를 얻는다."""
    if not hwnd_dialog or not IsWindow(hwnd_dialog):
        return ""
    old_clip = _get_clipboard_text()
    try:
        _send_hotkey(hwnd_dialog, win32con.VK_MENU, ord("D"), pre_delay=0.05, gap=0.03)
        time.sleep(0.05)
        _send_hotkey(hwnd_dialog, win32con.VK_CONTROL, ord("C"), pre_delay=0.02, gap=0.03)
        time.sleep(0.08)
        text = (_get_clipboard_text() or "").strip().strip('"')
        if _WIN_PATH_RE.match(text):
            p = pathlib.PureWindowsPath(text)
            return str(p)
    except Exception:
        pass
    finally:
        # 주소창 포커스를 원래대로 돌리기 위해 파일명 입력란으로 이동
        _send_hotkey(hwnd_dialog, win32con.VK_MENU, ord("N"), pre_delay=0.01, gap=0.02)
        if old_clip:
            try:
                _set_clipboard_text(old_clip)
            except Exception:
                pass
    return ""


def resolve_saved_filepath(filename, directory="", lookback_seconds=600):
    """대화상자에서 경로를 못 얻었을 때, 최근 저장 파일을 후보 폴더에서 역추적한다."""
    if not filename:
        return ""

    now = time.time()
    candidates = []
    roots = []

    if directory:
        roots.append(pathlib.Path(directory))

    home = pathlib.Path(os.path.expanduser("~"))
    userprofile = pathlib.Path(os.environ.get("USERPROFILE", str(home)))
    onedrive = pathlib.Path(os.environ.get("OneDrive", ""))
    roots.extend(
        [
            home / "Downloads",
            home / "Documents",
            home / "Desktop",
            userprofile / "Downloads",
            userprofile / "Documents",
            userprofile / "Desktop",
            pathlib.Path.cwd(),
        ]
    )
    if str(onedrive):
        roots.extend([onedrive / "Documents", onedrive / "Desktop"])

    seen = set()
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        if not root.exists() or not root.is_dir():
            continue
        try:
            for p in root.glob(f"{filename}*"):
                if not p.is_file():
                    continue
                try:
                    mtime = p.stat().st_mtime
                except Exception:
                    continue
                if now - mtime <= lookback_seconds:
                    candidates.append((mtime, str(p)))
            # 직접 하위 폴더도 제한적으로 탐색 (깊은 전체 검색은 피함)
            for child in root.iterdir():
                if not child.is_dir():
                    continue
                try:
                    for p in child.glob(f"{filename}*"):
                        if not p.is_file():
                            continue
                        mtime = p.stat().st_mtime
                        if now - mtime <= lookback_seconds:
                            candidates.append((mtime, str(p)))
                except Exception:
                    continue
        except Exception:
            continue

    if not candidates:
        return ""
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def get_save_dialog_directory(hwnd_dialog, filename="", retries=10, pause=0.08):
    """저장 대화 상자 텍스트 후보에서 디렉토리 경로를 추정한다."""
    if not hwnd_dialog or not IsWindow(hwnd_dialog):
        return ""

    for _ in range(max(1, retries)):
        # 0) 주소창 직접 복사
        addr = _get_save_dialog_directory_by_addressbar(hwnd_dialog)
        if addr:
            return str(pathlib.PureWindowsPath(addr))

        # 1) 공용 파일 대화상자 API 메시지로 직접 조회(가장 신뢰도 높음)
        folder = _get_dialog_text_by_cdm(hwnd_dialog, _CDM_GETFOLDERPATH)
        if folder:
            return str(pathlib.PureWindowsPath(folder))

        fullpath = _get_dialog_text_by_cdm(hwnd_dialog, _CDM_GETFILEPATH)
        if fullpath:
            p = pathlib.PureWindowsPath(fullpath)
            if p.parent and str(p.parent) not in (".", ""):
                return str(p.parent)

        # 2) 실패 시 기존 UI 텍스트 기반 추정
        candidates = []
        try:
            descendants = list(_descendants_dfs(hwnd_dialog))
        except Exception:
            descendants = []

        for h in descendants:
            if not h or not IsWindow(h):
                continue
            txt = _read_unicode_wnd_text(h).strip()
            if not txt:
                continue
            if filename and txt == filename:
                continue
            if _WIN_PATH_RE.match(txt):
                candidates.append(txt)

        if candidates:
            # 가장 긴 경로를 우선 채택
            best = sorted(candidates, key=len, reverse=True)[0]
            # 파일 경로가 잡힌 경우 parent로 변환
            if filename and best.lower().endswith(("\\" + filename).lower()):
                return str(pathlib.PureWindowsPath(best).parent)
            p = pathlib.PureWindowsPath(best)
            # 확장자가 있고 파일명처럼 보이면 parent를 반환
            if p.suffix and len(p.parts) >= 2:
                return str(p.parent)
            return str(p)

        time.sleep(pause)

    return ""


def find_kakao_search_edit():
    hwndkakao = FindWindow(None, "카카오톡")
    if not hwndkakao:
        return None

    hwndkakao_edit1 = win32gui.FindWindowEx(hwndkakao, None, "EVA_ChildWindow", None)
    if not hwndkakao_edit1:
        return None

    hwndkakao_edit2_1 = win32gui.FindWindowEx(hwndkakao_edit1, None, "EVA_Window", None)
    hwndkakao_edit2_2 = win32gui.FindWindowEx(hwndkakao_edit1, hwndkakao_edit2_1, "EVA_Window", None)
    if not hwndkakao_edit2_2:
        return None

    return win32gui.FindWindowEx(hwndkakao_edit2_2, None, "Edit", None)


def open_chatroom(chatroom_name):
    hwndkakao = FindWindow(None, "카카오톡")
    if not hwndkakao:
        raise RuntimeError("카카오톡 창을 찾을 수 없습니다.")

    # 카카오톡 창을 활성화하고 채팅 탭으로 이동 (Ctrl+2)
    try:
        win32gui.SetForegroundWindow(hwndkakao)
        win32gui.BringWindowToTop(hwndkakao)
        time.sleep(0.2)
        _send_hotkey(hwndkakao, win32con.VK_CONTROL, ord('2'))
        time.sleep(0.5)
    except Exception:
        # 로깅이 없으므로 일단 진행
        pass

    hwnd_search = find_kakao_search_edit()
    if not hwnd_search:
        raise RuntimeError("카카오톡 창 또는 검색 입력창을 찾을 수 없습니다.")

    # 검색창을 비우고, 검색어를 입력합니다.
    # WM_SETTEXT는 덮어쓰기지만, UI 상태를 확실히 초기화하기 위해 빈 문자열을 먼저 보냅니다.
    win32api.SendMessage(hwnd_search, win32con.WM_SETTEXT, 0, "")
    time.sleep(0.1)
    win32api.SendMessage(hwnd_search, win32con.WM_SETTEXT, 0, chatroom_name)
    time.sleep(0.5)
    SendReturn(hwnd_search)
    time.sleep(1.0)

    hwnd_chatroom = FindWindow(None, chatroom_name)
    if not hwnd_chatroom:
        raise RuntimeError(f"채팅방 '{chatroom_name}'을 열 수 없습니다.")
    return hwnd_chatroom


def find_chat_input(hwnd_chatroom):
    if not hwnd_chatroom or not IsWindow(hwnd_chatroom):
        return None
    return win32gui.FindWindowEx(hwnd_chatroom, None, "RICHEDIT50W", None)


def send_text_message(hwnd_chatroom, message):
    hwnd_input = find_chat_input(hwnd_chatroom)
    if not hwnd_input:
        raise RuntimeError("카카오톡 텍스트 입력 창을 찾을 수 없습니다.")

    _set_clipboard_text(str(message))
    PostKeyEx(hwnd_input, ord('A'), [w.VK_CONTROL], False)
    time.sleep(2)
    PostKeyEx(hwnd_input, ord('V'), [w.VK_CONTROL], False)
    time.sleep(2)
    PostKeyEx(hwnd_input, w.VK_RETURN, [], False)


def send_message(chatroom, message):
    hwnd_chatroom = open_chatroom(chatroom)
    path = pathlib.Path(str(message))
    if path.exists():
        dragFileToWnd(str(path.resolve()), hwnd_chatroom)
    else:
        send_text_message(hwnd_chatroom, message)

def extract_messages_from_chatroom(chatroom):
    hwnd_chatroom = None
    hwnd_dialog = None
    try:
        hwnd_chatroom = open_chatroom(chatroom)
        hwnd_list = win32gui.FindWindowEx(hwnd_chatroom, None, "EVA_VH_ListControl_Dblclk", None)
        if not hwnd_list:
            raise RuntimeError("카카오톡 메시지 리스트 컨트롤을 찾을 수 없습니다.")

        PostKeyEx(hwnd_list, ord('S'), [w.VK_CONTROL], False)
        time.sleep(2)
        
        hwnd_dialog = find_save_dialog(timeout=10)
        if not hwnd_dialog:
            raise RuntimeError("저장 대화 상자를 찾을 수 없습니다.")

        filename = get_save_dialog_filename(hwnd_dialog)
        if not filename:
            raise RuntimeError("저장 대화 상자에서 파일명을 얻을 수 없습니다.")
            
        directory = get_save_dialog_directory(hwnd_dialog, filename=filename)
        filepath = str(pathlib.PureWindowsPath(directory) / filename) if directory and filename else filename
        filepath = ensure_txt_filepath(filepath)

        print(f"저장 파일명: {filename}, 디렉토리: {directory}")

        send_alt_s(hwnd_dialog)
        time.sleep(0.5)

        hwnd_confirm = find_foreground_dialog(timeout=2)
        if hwnd_confirm and hwnd_confirm != hwnd_dialog:
            press_return(hwnd_confirm)
            wait_until_window_closed(hwnd_confirm, timeout=2)

        wait_until_window_closed(hwnd_dialog, timeout=3)
        time.sleep(1.0)

        resolved = resolve_saved_filepath(filename, directory=directory)
        if resolved:
            filepath = ensure_txt_filepath(resolved)
        
        filepath = rename_saved_file_with_chatroom(filepath, chatroom)
        
        content = read_saved_text_file(filepath)
        print(f"최종 저장 경로: {filepath}")
        if not content:
            print("경고: 저장된 파일의 내용을 읽지 못했습니다.")
        
        return filepath
    finally:
        if hwnd_dialog and win32gui.IsWindow(hwnd_dialog):
            win32gui.PostMessage(hwnd_dialog, win32con.WM_CLOSE, 0, 0)
        if hwnd_chatroom and win32gui.IsWindow(hwnd_chatroom):
            close_chatroom_window(hwnd_chatroom, chatroom_name=chatroom)

if __name__ == '__main__':
    if (len(sys.argv) > 1):
        chatroom = sys.argv[1]
    else:
        chatroom = '나에게 쓰기'
    print(extract_messages_from_chatroom(chatroom))