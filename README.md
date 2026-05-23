# 2PC With Presumed Commit - Global Inventory Update

Đây là đồ án môn Cơ sở dữ liệu phân tán với đề tài:

```text
2PC with Presumed Commit (PC): Global Inventory Update
```

Mục tiêu của đồ án là xây dựng hệ thống mô phỏng giao dịch phân tán cập nhật tồn kho toàn cục trên 4 site. Hệ thống sử dụng giao thức Two-Phase Commit với tối ưu Presumed Commit, có phân tích chi phí ACD (ACK of Commit) và so sánh số lượng thông điệp mạng giữa Presumed Abort và Presumed Commit.

## Kiến trúc tổng quan

Ở giai đoạn hiện tại, project đã thiết lập bộ khung API bằng FastAPI gồm 1 Coordinator và 4 Participant chạy trên máy cục bộ bằng nhiều process riêng biệt:

```text
Coordinator: http://127.0.0.1:8000
site_a:      http://127.0.0.1:8001  North
site_b:      http://127.0.0.1:8002  Central
site_c:      http://127.0.0.1:8003  SouthEast
site_d:      http://127.0.0.1:8004  Mekong
```

Mô hình nhiều process cục bộ được dùng để mô phỏng 4 site phân tán. Các phần xử lý dataset 5,000 dòng, SQLite, log phục hồi, state machine 2PC và biểu đồ message count sẽ được bổ sung ở các phần tiếp theo.

## Cài đặt môi trường

Tạo môi trường ảo và cài thư viện:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Nếu máy Windows không nhận lệnh `python`, dùng:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Chạy toàn bộ service

Chạy Coordinator và 4 Participant:

```powershell
.\scripts\run_all.ps1
```

Script sẽ mở các cửa sổ PowerShell riêng cho từng service.

## Kiểm tra service

Kiểm tra Coordinator:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Kiểm tra 4 Participant:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
Invoke-RestMethod http://127.0.0.1:8002/health
Invoke-RestMethod http://127.0.0.1:8003/health
Invoke-RestMethod http://127.0.0.1:8004/health
```

## Dừng service

```powershell
.\scripts\stop_all.ps1
```

## API Coordinator

```text
GET  /health
POST /transactions/global-inventory-update
GET  /transactions/{transaction_id}
GET  /transactions/{transaction_id}/decision
GET  /metrics/messages
POST /metrics/reset
POST /debug/forget-transaction/{transaction_id}
```

## API Participant

```text
GET  /health
POST /prepare
POST /global-commit
POST /global-abort
POST /recover-pending
POST /debug/crash-after-ready
POST /debug/crash-after-global-commit
GET  /inventory/{inventory_id}
GET  /logs/{transaction_id}
```

## Trạng thái hiện tại

Project hiện đã có:

```text
coordinator/
participant/
scripts/
runtime/
requirements.txt
README.md
```

Các API hiện tại là stub ổn định để chuẩn bị cho các phần tiếp theo. Phần sau sẽ bổ sung tạo dataset 5,000 dòng, phân mảnh dữ liệu theo vùng, SQLite cục bộ cho từng site, log JSONL, recovery sau crash và logic Presumed Commit đầy đủ.
