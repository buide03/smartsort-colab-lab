# Deploy SmartSort trên Oracle Always Free

Train vẫn ở Colab GPU. VM Ubuntu chạy Docker CPU để phục vụ giao diện, validation, chốt model, test và báo cáo. Caddy làm reverse proxy, cấp/gia hạn chứng chỉ HTTPS. Dữ liệu nằm trên ổ VM, không phụ thuộc filesystem của container.

## 1. Phần giáo viên cần thực hiện trước

Bạn chưa có tài khoản/VM. Đăng ký tại [Oracle Cloud Free](https://www.oracle.com/cloud/free/). Giáo viên tự nhập thông tin cá nhân, điện thoại, thẻ xác minh và OTP trong trang Oracle; không gửi thông tin thẻ, mật khẩu hay OTP vào chat. Oracle cho biết thẻ không bị tính phí nếu không nâng cấp tài khoản: [điều kiện đăng ký](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm).

Chọn home region cẩn thận: tài nguyên Always Free phải nằm ở home region. Tài liệu hiện tại ghi Ampere A1 tổng **2 OCPU / 12 GB RAM**, tổng ổ boot và block volume **200 GB**; kiểm tra nhãn Always Free Eligible khi tạo, không chọn máy trả phí hoặc nâng cấp để vượt hạn mức. Nếu hết capacity, thử availability domain khác trong home region hoặc chờ. Máy ít hoạt động có thể bị thu hồi; giữ bản sao lưu ngoài VM. [Hạn mức và điều kiện Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

## 2. Tạo VM và mạng

Trong Oracle Console, mở **Compute → Instances → Create instance**; các nhãn có thể thay đổi theo giao diện:

1. Đặt tên `smartsort-classroom`.
2. Chọn image **Ubuntu 24.04**, kiến trúc ARM64 tương ứng shape **VM.Standard.A1.Flex**.
3. Chọn **2 OCPU, 12 GB RAM**, boot volume **50 GB**, xác nhận thuộc Always Free và tổng tài nguyên tài khoản không vượt hạn mức.
4. Dùng VCN có public subnet, Internet Gateway và route `0.0.0.0/0` tới Internet Gateway; cấp public IPv4 cho VM.
5. Tạo/cung cấp SSH public key, lưu private key trên máy giáo viên. Không commit khóa vào repo.
6. Chờ VM Running; ghi lại IP public. Ubuntu dùng username SSH **`ubuntu`**. [Hướng dẫn tạo instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/launchinginstance.htm).

Tại Security List hoặc NSG áp dụng cho subnet/VNIC, thêm ingress **stateful TCP** (source port: All):

| Source CIDR | Destination port | Mục đích |
|---|---|---|
| IP internet của giáo viên `/32` | 22 | SSH quản trị |
| `0.0.0.0/0` | 80 | Cấp chứng chỉ và chuyển sang HTTPS |
| `0.0.0.0/0` | 443 | Học sinh truy cập HTTPS |

Giữ egress cần thiết cho DNS, HTTPS, tải package/image. Ứng dụng không publish port 8000 ra internet; chỉ Caddy mở 80/443. Nếu IP internet của giáo viên thay đổi, sửa rule SSH `/32` cho IP mới.

Kết nối từ PowerShell trên máy giáo viên, thay IP và đường dẫn bằng giá trị thật:

```powershell
ssh -i "C:\duong-dan\oracle-private.key" ubuntu@IP_PUBLIC_THAT
```

## 3. Tên miền HTTPS

Nếu đã có tên miền, tạo DNS record **A** của subdomain trỏ đến IP public VM. Không tạo AAAA nếu chưa cấu hình IPv6.

Nếu chưa có tên miền, có thể đăng ký subdomain miễn phí tại [DuckDNS](https://www.duckdns.org/): đăng nhập, chọn tên còn trống và cập nhật IP của subdomain thành IP public VM. Ví dụ `ten-lab-cua-ban.duckdns.org` chỉ là mẫu; dùng tên thật được cấp. Nếu IP VM đổi, cập nhật DNS trước khi dùng lại URL.

Caddy cần hostname trỏ đúng VM và port 80/443 truy cập được từ internet để cấp chứng chỉ. [HTTPS của Caddy](https://caddyserver.com/docs/quick-starts/https). Chứng chỉ public thật chỉ được xác minh khi có VM/domain; CI dùng chứng chỉ nội bộ để kiểm tra proxy.

## 4. Cài Docker và chạy lab trên VM

Các lệnh dưới đây chạy **trong SSH của VM**, không chạy trong PowerShell Windows:

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/buide03/smartsort-colab-lab.git
cd smartsort-colab-lab
sudo bash deploy/oracle/install-docker-ubuntu.sh
cp deploy/oracle/.env.example deploy/oracle/.env
chmod 600 deploy/oracle/.env
nano deploy/oracle/.env
```

Installer dành cho VM Ubuntu 24.04 mới, dùng apt repository chính thức của Docker. Nếu VM có Docker/package container khác, dùng [hướng dẫn Docker Ubuntu](https://docs.docker.com/engine/install/ubuntu/) để xử lý xung đột trước.

Sửa hai dòng bắt buộc:

```dotenv
SMARTSORT_DOMAIN=ten-subdomain-that-cua-ban.duckdns.org
SMARTSORT_CLASSROOM_PASSWORD=ma-lop-it-nhat-10-ky-tu
```

Đổi thành mã riêng của lớp. Password có ký tự `$` cần bao trong dấu nháy đơn theo cú pháp dotenv để tránh Compose nội suy. Không dùng nguyên password mẫu. Biến `SMARTSORT_DATA_DIR=/opt/smartsort/data` giữ nguyên cho VM mới.

```bash
sudo bash deploy/oracle/deploy.sh
sudo docker compose -f deploy/oracle/compose.yaml logs --tail=100 caddy
```

Script kiểm tra hostname/password, build image phù hợp kiến trúc VM, chạy app và Caddy. Bind mount `/opt/smartsort/data:/data` giữ ảnh, nhãn, split, model và báo cáo trên VM. Caddy lưu trạng thái chứng chỉ trong Docker volume riêng.

Nếu bị timeout internet dù OCI đã mở cổng, kiểm tra firewall trên Ubuntu. Với image có iptables rule chặn ingress, thêm rule trước rule REJECT, giữ nguyên SSH:

```bash
sudo iptables -I INPUT 1 -p tcp -m multiport --dports 80,443 -j ACCEPT
```

Nếu dùng `netfilter-persistent`, lưu rule bằng `sudo netfilter-persistent save`; kiểm tra lại sau reboot. Không tắt toàn bộ firewall để sửa lỗi. Docker có quy tắc forwarding riêng; xem [Docker và firewall](https://docs.docker.com/engine/install/ubuntu/#firewall-limitations) khi dùng UFW.

## 5. Kiểm tra URL và dùng cho lớp

1. Mở `https://TEN_DOMAIN_THAT/healthz`, phải thấy `{"status":"ok"}` và chứng chỉ được trình duyệt tin cậy.
2. Mở trang chính bằng cửa sổ ẩn danh: đăng nhập username **`class`**, password đã đặt trong `.env`.
3. Tạo phiên thử và hoàn thành một vòng: ảnh → gán nhãn → chia tập → xuất train → Colab GPU → nhập model → validation → chốt → test → tải ZIP báo cáo.
4. Chờ tác vụ hoàn tất, restart app rồi mở lại phiên để xác nhận dữ liệu vẫn còn:

```bash
sudo docker compose -f deploy/oracle/compose.yaml restart smartsort
```

5. Gửi URL HTTPS và mã lớp riêng cho học sinh.

Lớp 40 học sinh nên dùng **8–10 nhóm**, mỗi nhóm tạo phiên có tên rõ ràng. Mọi nhóm nhìn thấy danh sách phòng học chung; chưa có tài khoản/quyền riêng theo học sinh. Một validation/test/suy luận chạy tại một thời điểm; server báo bận cho nhóm khác, không tự xếp hàng. Thời gian phụ thuộc số ảnh/checkpoint. Giới hạn mặc định mỗi phiên 1.000 ảnh, mỗi lượt upload 64 MB; mỗi ảnh tối đa 25 MB và 20 triệu pixel. Chưa đo tải 40 người đồng thời trên VM Oracle.

## 6. Cập nhật, sao lưu và phục hồi

Chỉ cập nhật/sao lưu khi lớp không có tác vụ đang chạy. Từ thư mục repo trên VM:

```bash
sudo bash deploy/oracle/backup.sh
git pull --ff-only
sudo bash deploy/oracle/deploy.sh
```

Backup dừng app ngắn hạn và tự khởi động lại, lưu archive tại `/opt/smartsort/backups/`. Tải archive về máy giáo viên để có bản sao ngoài VM:

```powershell
scp -i "C:\duong-dan\oracle-private.key" ubuntu@IP_PUBLIC_THAT:~/smartsort-backup.tar.gz .
```

Trước lệnh `scp`, trong SSH sao chép backup thật thành file thuộc tài khoản `ubuntu`:

```bash
sudo cp /opt/smartsort/backups/TEN_BACKUP_THAT.tar.gz ~/smartsort-backup.tar.gz
sudo chown ubuntu:ubuntu ~/smartsort-backup.tar.gz
chmod 600 ~/smartsort-backup.tar.gz
```

Phục hồi trên VM mới: cài app, đặt đúng data directory, dừng app rồi giải nén archive vào thư mục dữ liệu và chạy lại. Trên VM còn dữ liệu, sao lưu trước và phục hồi vào thư mục rỗng khác rồi đổi `SMARTSORT_DATA_DIR`; không ghi đè phiên hiện có. Backup chứa ảnh/model/kết quả, không chứa `.env` hoặc chứng chỉ Caddy; giữ cấu hình/password riêng và Caddy sẽ cấp lại chứng chỉ.

Không xóa VM/boot volume/data directory khi còn cần dữ liệu. `docker compose down` giữ bind mount, nhưng xóa ổ VM sẽ mất dữ liệu. Theo dõi disk/RAM và giới hạn tài khoản Oracle; Always Free có điều kiện và không cam kết tính sẵn sàng cho giờ dạy.

## 7. Trạng thái triển khai

Repo có workflow **Docker deployment checks**, chạy trên cả x86_64 và ARM64: build CPU image, suy luận EfficientNet, HTTP workflow, Caddy HTTPS proxy và dữ liệu qua việc thay container. Xem [Actions](https://github.com/buide03/smartsort-colab-lab/actions) và đợi các job xanh.

Đây là bộ cấu hình sẵn để triển khai; chưa có VM Oracle hoặc URL public thật khi giáo viên chưa tạo tài khoản/VM. Sau khi tạo, cung cấp IP public, username SSH, đường dẫn private key trên máy giáo viên và hostname DNS để tiếp tục triển khai trực tiếp. Không gửi nội dung private key vào chat.
