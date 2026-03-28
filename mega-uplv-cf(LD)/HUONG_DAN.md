# Hướng dẫn sử dụng AutoClickTool

Công cụ này giúp bạn tự động hóa các thao tác trên màn hình máy tính dựa trên hình ảnh hoặc tọa độ cố định.

## 1. Cài đặt môi trường (Yêu cầu)

Bạn cần có Python trên máy tính. Sau đó, mở Terminal/Command Prompt và chạy lệnh sau để cài đặt các thư viện cần thiết:

```bash
pip install pyautogui opencv-python
```

## 2. Chuẩn bị hình ảnh

Để công cụ có thể tìm và click vào các nút trên màn hình, bạn cần chụp ảnh các nút đó (ví dụ: nút "Play", nút "Close").

1.  Dùng công cụ chụp màn hình (Snipping Tool trên Windows).
2.  Chụp chính xác hình ảnh của nút cần click.
3.  Lưu hình ảnh vào thư mục `images/` bên trong thư mục `AutoClickTool`.
    *   Ví dụ: `c:/Work/Freelancer/ToolProxy/AutoClickTool/images/btn_play.png`

## 3. Cấu hình kịch bản (script.json)

Mở file `script.json` để thiết lập các bước chạy. Mỗi bước là một đối tượng trong danh sách:

### Các hành động hỗ trợ:

*   **`click_image`**: Tìm hình ảnh trên màn hình và click.
    *   `target`: Đường dẫn đến file ảnh (ví dụ: `"images/btn_play.png"`).
    *   `timeout`: Thời gian tối đa (giây) để chờ hình ảnh xuất hiện.
    *   `confidence`: Độ chính xác khi tìm ảnh (từ 0.1 đến 1.0, mặc định là 0.8).
*   **`wait`**: Tạm dừng một khoảng thời gian.
    *   `duration`: Số giây cần chờ.
*   **`click_fixed`**: Click vào một tọa độ cố định trên màn hình.
    *   `x`, `y`: Tọa độ cần click.

### Ví dụ script.json:
```json
[
  {
    "action": "click_image",
    "target": "images/btn_game.png",
    "timeout": 180
  },
  {
    "action": "wait",
    "duration": 5
  },
  {
    "action": "click_fixed",
    "x": 100,
    "y": 200
  }
]
```

## 4. Cách chạy công cụ

Khi đã chuẩn bị xong hình ảnh và file cấu hình, hãy mở Terminal trong thư mục `AutoClickTool` và chạy:

```bash
python main.py
```

Công cụ sẽ thực hiện từng bước trong kịch bản và in thông báo ra màn hình.

## 5. Lưu ý an toàn (Dừng khẩn cấp)

Trong trường hợp công cụ click nhầm hoặc bạn muốn dừng ngay lập tức:
*   **Di chuyển chuột thật nhanh về góc trên cùng bên trái của màn hình (tọa độ 0,0).**
*   Hành động này sẽ kích hoạt tính năng `FAILSAFE` của thư viện và dừng chương trình ngay lập tức.
