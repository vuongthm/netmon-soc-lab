# Server01 — BIND9 DNS and vsftpd FTP server

**Node:** Server01 · Ubuntu 20.04 · `10.20.201.10/24`  
**Default gateway:** `10.20.201.1` (pfSense DMZ2)  
**Services:** BIND9 authoritative zone `lab.local`, vsftpd, Node Exporter and optional mtail.

## 1. Configure the network

```bash
sudo tee /etc/netplan/01-netcfg.yaml << 'EOF'
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: false
      addresses: [10.20.201.10/24]
      gateway4: 10.20.201.1
      nameservers:
        addresses: [127.0.0.1, 8.8.8.8]
        search: [lab.local]
EOF
sudo netplan apply
# Verify
ip addr show eth0
ping -c 3 10.20.201.1
ping -c 3 8.8.8.8
```

## 2. Install and configure BIND9

```bash
sudo apt update
sudo apt install -y bind9 bind9utils
# Configure named.conf.options
sudo tee /etc/bind/named.conf.options << 'EOF'
options {
    directory "/var/cache/bind";
    recursion yes;
    allow-query { any; };
    forwarders { 8.8.8.8; 8.8.4.4; };
    dnssec-validation auto;
    listen-on { any; };
};
EOF
# Create the lab.local zone
sudo tee -a /etc/bind/named.conf.local << 'EOF'
zone "lab.local" {
    type master;
    file "/etc/bind/zones/db.lab.local";
};
EOF
sudo mkdir -p /etc/bind/zones
sudo tee /etc/bind/zones/db.lab.local << 'EOF'
$TTL    604800
@       IN      SOA     dns.lab.local. admin.lab.local. (
                        2024042601 ; Serial
                        604800     ; Refresh
                        86400      ; Retry
                        2419200    ; Expire
                        604800 )   ; Negative Cache TTL
;
; Name servers
@       IN      NS      dns.lab.local.
; A records
dns     IN      A       10.20.201.10
ftp     IN      A       10.20.201.10
web     IN      A       10.20.200.10
www     IN      A       10.20.200.10
server01 IN     A       10.20.201.10
server02 IN     A       10.20.200.10
EOF
sudo named-checkconf
sudo named-checkzone lab.local /etc/bind/zones/db.lab.local
sudo systemctl enable bind9
sudo systemctl restart bind9
# Test DNS
dig @10.20.201.10 web.lab.local
dig @10.20.201.10 ftp.lab.local
```

The local zone contains the A records for `dns`, `ftp`, `web`, `www`, `server01`, and `server02`. The command appends the zone declaration to `/etc/bind/named.conf.local`; avoid appending it a second time during reinstallation.

## 3. Install vsftpd

```bash
sudo apt install -y vsftpd
sudo tee /etc/vsftpd.conf << 'EOF'
listen=YES
listen_ipv6=NO
anonymous_enable=NO
local_enable=YES
write_enable=YES
local_umask=022
dirmessage_enable=YES
use_localtime=YES
xferlog_enable=YES
connect_from_port_20=YES
chroot_local_user=YES
allow_writeable_chroot=YES
secure_chroot_dir=/var/run/vsftpd/empty
pam_service_name=vsftpd
pasv_enable=YES
pasv_min_port=30000
pasv_max_port=30100
EOF
# Create a lab-only FTP account
sudo useradd -m ftpuser
echo "ftpuser:ftppass" | sudo chpasswd
sudo systemctl enable vsftpd
sudo systemctl restart vsftpd
# Test FTP
ftp -n 10.20.201.10 << 'EOF'
user ftpuser ftppass
quit
EOF
```

**Security note:** `ftpuser:ftppass` is an intentionally weak **lab-only** credential in the project procedure. Do not publish or reuse it on a production host; FTP is clear-text unless separately protected.

## 4. Install Node Exporter

```bash
# Install the same Node Exporter version used on Server02
cd /tmp
wget -q https://github.com/prometheus/node_exporter/releases/download/v1.8.0/node_exporter-1.8.0.linux-amd64.tar.gz
tar xzf node_exporter-1.8.0.linux-amd64.tar.gz
sudo cp node_exporter-1.8.0.linux-amd64/node_exporter /usr/local/bin/
sudo useradd -rs /bin/false node_exporter 2>/dev/null || true
sudo tee /etc/systemd/system/node_exporter.service << 'EOF'
[Unit]
Description=Node Exporter
After=network.target
[Service]
User=node_exporter
ExecStart=/usr/local/bin/node_exporter
Restart=always
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now node_exporter
curl http://localhost:9100/metrics | head -3
```

## 5. Install and configure mtail for service logs

The document defines mtail programs and services on Server01 but does not repeat the mtail binary installation here. Install the same 3.0.8 binary used for Server02 first:

```bash
cd /tmp
wget -q https://github.com/google/mtail/releases/download/v3.0.8/mtail_3.0.8_linux_amd64.tar.gz
tar xzf mtail_3.0.8_linux_amd64.tar.gz
sudo cp mtail /usr/local/bin/
```

Then configure the DNS/FTP programs and service units:

```bash
sudo mkdir -p /etc/mtail
# DNS log parser
sudo tee /etc/mtail/dns.mtail << 'EOF'
counter dns_queries_total by type
/queries: (?P<type>\w+)/ {
  dns_queries_total[$type]++
}
EOF
# FTP log parser
sudo tee /etc/mtail/ftp.mtail << 'EOF'
counter ftp_logins_total by result
/OK LOGIN/ {
  ftp_logins_total["success"]++
}
/FAIL LOGIN/ {
  ftp_logins_total["fail"]++
}
EOF
# mtail DNS service
sudo tee /etc/systemd/system/mtail-dns.service << 'EOF'
[Unit]
Description=mtail for DNS
After=network.target bind9.service
[Service]
ExecStart=/usr/local/bin/mtail \
  --progs /etc/mtail/dns.mtail \
  --logs /var/log/syslog \
  --port 3904
Restart=always
[Install]
WantedBy=multi-user.target
EOF
# mtail FTP service
sudo tee /etc/systemd/system/mtail-ftp.service << 'EOF'
[Unit]
Description=mtail for FTP
After=network.target vsftpd.service
[Service]
ExecStart=/usr/local/bin/mtail \
  --progs /etc/mtail/ftp.mtail \
  --logs /var/log/vsftpd.log \
  --port 3905
Restart=always
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now mtail-dns mtail-ftp
```

**Important:** These parsers depend on actual log files and log formats. In particular, the BIND9 `queries:` log pattern needs query logging and an appropriate log destination. Verify log presence and parser output rather than assuming the series appears immediately.

## 6. Validate DNS, FTP and metrics

```bash
sudo named-checkconf
sudo named-checkzone lab.local /etc/bind/zones/db.lab.local
dig @10.20.201.10 web.lab.local +short
curl -fsS http://10.20.201.10:9100/metrics | head
curl -fsS http://10.20.201.10:3904/metrics | head
curl -fsS http://10.20.201.10:3905/metrics | head
```

Only authorized lab clients should be able to reach FTP and the metrics endpoints.
