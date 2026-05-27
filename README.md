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

## Chuẩn bị dữ liệu và phân mảnh

Tạo dataset tồn kho toàn cục đúng 5,000 dòng:

```powershell
python scripts/generate_dataset.py
```

Phân mảnh ngang chính quy theo `region` thành 4 site:

```powershell
python scripts/partition_dataset.py
```

Kiểm chứng các tính chất theo Chương 2:

```powershell
python scripts/verify_fragmentation.py
```

Chạy test phân mảnh:

```powershell
python -m pytest tests/test_fragmentation.py
```

Dữ liệu được tạo theo mô hình:

```text
20 warehouses x 250 SKUs = 5,000 inventory rows
```

Phân bổ site:

```text
site_a -> North     -> WH001-WH005
site_b -> Central   -> WH006-WH010
site_c -> SouthEast -> WH011-WH015
site_d -> Mekong    -> WH016-WH020
```

Phân mảnh dùng primary horizontal fragmentation:

```text
Inventory_North     = select region='North' from Warehouse_Inventory
Inventory_Central   = select region='Central' from Warehouse_Inventory
Inventory_SouthEast = select region='SouthEast' from Warehouse_Inventory
Inventory_Mekong    = select region='Mekong' from Warehouse_Inventory
```

Script `verify_fragmentation.py` kiểm tra:

```text
Completeness
Reconstruction
Disjointness
Predicate correctness
Warehouse allocation
```

## Giao thức 2PC và nhật ký hệ thống

Phần cốt lõi hiện đã có state machine 2PC ở mức protocol/log:

```text
PREPARE
VOTE_COMMIT
VOTE_ABORT
GLOBAL_COMMIT
GLOBAL_ABORT
ACK_COMMIT
ACK_ABORT
RECOVERY_QUERY
RECOVERY_DECISION
```

Coordinator điều phối giao dịch qua:

```text
POST /transactions/global-inventory-update
```

Participant xử lý:

```text
POST /prepare
POST /global-commit
POST /global-abort
POST /recover-pending
```

Nhật ký bền vững được ghi dạng JSONL:

```text
runtime/coordinator/coordinator_log.jsonl
runtime/site_a/site_a_log.jsonl
runtime/site_b/site_b_log.jsonl
runtime/site_c/site_c_log.jsonl
runtime/site_d/site_d_log.jsonl
```

Theo Presumed Commit, Coordinator không ghi durable log cho `GLOBAL_COMMIT`. Nếu Participant recovery từ trạng thái `READY` và Coordinator trả `NOT_FOUND`, Participant suy luận kết quả là `COMMIT`.

Chạy test protocol và log:

```powershell
python -m pytest tests/test_log_store.py
python -m pytest tests/test_protocol_state.py
python -m pytest tests/test_presumed_commit.py
```

Chạy toàn bộ test hiện có:

```powershell
python -m pytest tests
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
data/
participant/
scripts/
tests/
runtime/
requirements.txt
README.md
```

Các API hiện tại là stub ổn định để chuẩn bị cho các phần tiếp theo. Dataset 5,000 dòng và 4 file phân mảnh theo vùng đã được chuẩn bị. Các phần sau sẽ bổ sung SQLite cục bộ cho từng site, log JSONL, recovery sau crash và logic Presumed Commit đầy đủ.
