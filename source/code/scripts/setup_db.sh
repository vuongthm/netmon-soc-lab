#!/bin/bash
# =============================================================================
# scripts/setup_db.sh
# Cài đặt PostgreSQL và tạo database/user cho NetMon SOC.
# Chạy với quyền sudo: sudo bash scripts/setup_db.sh
# Tương thích: Ubuntu 24.04
# =============================================================================

set -e  # dừng ngay nếu có lỗi

# ── Màu sắc terminal ────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Kiểm tra root ────────────────────────────────────────────────────
[ "$EUID" -ne 0 ] && error "Chạy với sudo: sudo bash scripts/setup_db.sh"

# ── Cấu hình ─────────────────────────────────────────────────────────
DB_NAME="netmon"
DB_USER="netmon"
DB_PASS="${NETMON_DB_PASSWORD:-netmon_secure_2024}"  # override bằng env var

echo ""
echo "══════════════════════════════════════════════"
echo "   NetMon SOC — PostgreSQL Setup"
echo "══════════════════════════════════════════════"
echo ""

# ── Bước 1: Cài PostgreSQL (chỉ nếu chưa có) ────────────────────────
if [ -e "/usr/bin/psql" ] || [ -e "/usr/local/bin/psql" ]; then
    success "PostgreSQL đã được cài sẵn — bỏ qua bước cài đặt"
else
    info "Dừng packagekitd để tránh apt lock..."
    systemctl stop packagekit 2>/dev/null || true
    systemctl stop unattended-upgrades 2>/dev/null || true

    # Chờ lock giải phóng (tối đa 60 giây)
    info "Chờ apt lock giải phóng..."
    for i in $(seq 1 60); do
        if ! fuser /var/lib/apt/lists/lock /var/lib/dpkg/lock-frontend &> /dev/null; then
            break
        fi
        echo -n "."
        sleep 1
    done
    echo ""

    # Xóa lock file nếu vẫn còn treo
    rm -f /var/lib/apt/lists/lock
    rm -f /var/lib/dpkg/lock-frontend
    rm -f /var/lib/dpkg/lock
    rm -f /var/cache/apt/archives/lock

    info "Cài PostgreSQL..."
    apt update -qq
    apt install -y postgresql postgresql-client libpq-dev > /dev/null
    success "PostgreSQL đã cài xong"
fi

# ── Bước 2: Khởi động service ────────────────────────────────────────
info "Kiểm tra PostgreSQL service..."
systemctl enable postgresql --quiet
systemctl start postgresql 2>/dev/null || true

# Chờ PostgreSQL sẵn sàng (tối đa 15 giây)
for i in $(seq 1 15); do
    if sudo -u postgres /usr/bin/psql -c "SELECT 1" &> /dev/null; then
        break
    fi
    sleep 1
done

if ! sudo -u postgres /usr/bin/psql -c "SELECT 1" &> /dev/null; then
    error "PostgreSQL không khởi động được sau 15 giây"
fi

success "PostgreSQL service đang chạy"

# ── Bước 3: Tạo user và database ────────────────────────────────────
info "Tạo database user '${DB_USER}'..."

sudo -u postgres /usr/bin/psql -c "
  DO \$\$
  BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
      CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';
      RAISE NOTICE 'User ${DB_USER} đã được tạo';
    ELSE
      ALTER USER ${DB_USER} WITH PASSWORD '${DB_PASS}';
      RAISE NOTICE 'User ${DB_USER} đã tồn tại, đã cập nhật password';
    END IF;
  END
  \$\$;
"

info "Tạo database '${DB_NAME}'..."
DB_EXISTS=$(sudo -u postgres /usr/bin/psql -tAc "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}';")
if [ "$DB_EXISTS" != "1" ]; then
    sudo -u postgres /usr/bin/psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
    success "Database '${DB_NAME}' đã được tạo"
else
    warn "Database '${DB_NAME}' đã tồn tại — bỏ qua"
fi

sudo -u postgres /usr/bin/psql -c "GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};"
success "Database '${DB_NAME}' sẵn sàng"

# ── Bước 4: Tối ưu PostgreSQL cho monitoring workload ────────────────
info "Tối ưu cấu hình PostgreSQL..."

PG_CONF=$(sudo -u postgres /usr/bin/psql -t -c "SHOW config_file;" | tr -d ' ')

# Chỉ thêm nếu chưa có block tối ưu của NetMon
if ! grep -q "NetMon SOC optimizations" "$PG_CONF"; then
    TOTAL_MEM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    SHARED_BUFS_MB=$((TOTAL_MEM_KB / 1024 / 4))
    EFFECTIVE_CACHE_MB=$((TOTAL_MEM_KB / 1024 * 3 / 4))

    cat >> "$PG_CONF" << EOF

# ── NetMon SOC optimizations ──
shared_buffers = ${SHARED_BUFS_MB}MB
effective_cache_size = ${EFFECTIVE_CACHE_MB}MB
work_mem = 16MB
maintenance_work_mem = 128MB
max_connections = 50
checkpoint_completion_target = 0.9
wal_buffers = 16MB
log_min_duration_statement = 1000
EOF

    systemctl restart postgresql

    # Chờ restart xong
    for i in $(seq 1 15); do
        if sudo -u postgres /usr/bin/psql -c "SELECT 1" &> /dev/null; then
            break
        fi
        sleep 1
    done

    success "PostgreSQL đã được tối ưu"
else
    warn "Cấu hình tối ưu đã tồn tại — bỏ qua"
fi

# ── Bước 5: Test kết nối ─────────────────────────────────────────────
info "Kiểm tra kết nối..."
if PGPASSWORD="${DB_PASS}" /usr/bin/psql -U "${DB_USER}" -d "${DB_NAME}" -h localhost -c "SELECT version();" > /dev/null 2>&1; then
    success "Kết nối thành công!"
else
    error "Kết nối thất bại — kiểm tra lại pg_hba.conf"
fi

# ── Bước 6: Tạo file .env ────────────────────────────────────────────
info "Kiểm tra file .env..."
ENV_FILE="$(dirname "$0")/../.env"

if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$(dirname "$0")/../.env.example" ]; then
        cp "$(dirname "$0")/../.env.example" "$ENV_FILE"
        sed -i "s|postgresql://netmon:netmon@localhost:5432/netmon|postgresql://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}|g" "$ENV_FILE"
        success ".env đã được tạo từ .env.example"
        warn "Nhớ điền TELEGRAM_BOT_TOKEN và GROQ_API_KEY trong file .env!"
    else
        cat > "$ENV_FILE" << EOF
DATABASE_URL=postgresql://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}
TELEGRAM_BOT_TOKEN=
GROQ_API_KEY=
PROMETHEUS_URL=http://localhost:9090
EOF
        success ".env đã được tạo mới (cần điền thêm thông tin)"
        warn "Nhớ điền TELEGRAM_BOT_TOKEN và GROQ_API_KEY trong file .env!"
    fi
else
    warn ".env đã tồn tại — không ghi đè"
fi

# ── Tóm tắt ──────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════"
echo -e "   ${GREEN}✔ Setup hoàn tất!${NC}"
echo "══════════════════════════════════════════════"
echo ""
echo "  Database : ${DB_NAME}"
echo "  User     : ${DB_USER}"
echo "  Password : ${DB_PASS}"
echo "  URL      : postgresql://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}"
echo ""
echo "  Bước tiếp theo:"
echo "  1. Điền thông tin vào .env"
echo "  2. pip install -r requirements.txt"
echo "  3. python app.py"
echo ""