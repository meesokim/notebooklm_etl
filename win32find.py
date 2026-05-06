import win32gui

def print_window_hierarchy(hwnd, depth=0):
    class_name = win32gui.GetClassName(hwnd)
    title = win32gui.GetWindowText(hwnd)
    print("  " * depth + f"[HWND: {hwnd}] Class: {class_name}, Title: {title}")
    
    # 자식 윈도우들을 찾아서 재귀적으로 출력
    children = []
    win32gui.EnumChildWindows(hwnd, lambda h, l: l.append(h), children)

    # 2. 자식 윈도우(채팅방 목록 등) 열거
    def enum_child_windows(hwnd, results):
        title = win32gui.GetWindowText(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        if title: # 제목이 있는 창만 출력
            print(f"핸들: {hwnd}, 클래스: {class_name}, 제목: {title}")
        return True

    print("--- 자식 창 목록 ---")
    win32gui.EnumChildWindows(hwnd, enum_child_windows, None)    
    # EnumChildWindows는 모든 하위 자식을 가져오므로, 
    # 직계 자식만 걸러내기 위해 별도의 로직이 필요할 수 있습니다.
    # 여기서는 단순 구조 파악을 위해 상위 몇 개만 확인하는 용도로 사용하세요.

# 카카오톡 메인 핸들 찾기
main_hwnd = win32gui.FindWindow(None, "카카오톡")
print(main_hwnd)
if main_hwnd:
    print_window_hierarchy(main_hwnd, 2)
else:
    print("카카오톡을 찾을 수 없습니다.")