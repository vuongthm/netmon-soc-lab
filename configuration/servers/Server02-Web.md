# Server02 — Nginx web server

**Node:** Server02 · Ubuntu 20.04 · `10.20.200.10/24`  
**Default gateway:** `10.20.200.1` (pfSense DMZ1)  
**Services:** Nginx, Node Exporter, optional mtail for Nginx logs.

## 1. Static network configuration

Edit `/etc/netplan/01-netcfg.yaml` using the following documented commands.

```bash
# /etc/netplan/01-netcfg.yaml
sudo tee /etc/netplan/01-netcfg.yaml << 'EOF'
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: false
      addresses: [10.20.200.10/24]
      gateway4: 10.20.200.1
      nameservers:
        addresses: [10.20.201.10, 8.8.8.8]
        search: [lab.local]
EOF
sudo netplan apply
# Verify
ip addr show eth0
ping -c 3 10.20.200.1   # ping gateway pfSense
ping -c 3 8.8.8.8       # ping internet
```

## 2. Nginx website

```bash
sudo apt update
sudo apt install -y nginx
# Create a simple test website
sudo tee /var/www/html/index.html << 'EOF'
<!DOCTYPE html>
<html>
<head><title>NetMon Lab — Server02</title></head>
<body>
  <h1>Server02 — Web Server</h1>
  <p>IP: 10.20.200.10 | Lab: NetMon SOC</p>
</body>
</html>
EOF
sudo systemctl enable nginx
sudo systemctl start  nginx
# Test
curl http://localhost
curl http://10.20.200.10
```

## 3. Node Exporter

```bash
cd /tmp
wget -q https://github.com/prometheus/node_exporter/releases/download/v1.8.0/node_exporter-1.8.0.linux-amd64.tar.gz
tar xzf node_exporter-1.8.0.linux-amd64.tar.gz
sudo cp node_exporter-1.8.0.linux-amd64/node_exporter /usr/local/bin/
sudo useradd -rs /bin/false node_exporter
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
# Test
curl http://localhost:9100/metrics | grep node_cpu | head -3
```

The exporter serves metrics on TCP/9100 and is scraped by Prometheus job `node-server02`.

## 4. Nginx metrics via mtail

```bash
cd /tmp
wget -q https://github.com/google/mtail/releases/download/v3.0.8/mtail_3.0.8_linux_amd64.tar.gz
tar xzf mtail_3.0.8_linux_amd64.tar.gz
sudo cp mtail /usr/local/bin/
# Create the mtail program for Nginx
sudo mkdir -p /etc/mtail
sudo tee /etc/mtail/nginx.mtail << 'EOF'
# Parse Nginx access log
counter http_requests_total by method, status
gauge active_connections
/^(?P<client>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] "(?P<method>\S+) \S+ \S+" (?P<status>\d+)/ {
  http_requests_total[$method][$status]++
}
EOF
sudo tee /etc/systemd/system/mtail-nginx.service << 'EOF'
[Unit]
Description=mtail for Nginx
After=network.target nginx.service
[Service]
ExecStart=/usr/local/bin/mtail \
  --progs /etc/mtail/nginx.mtail \
  --logs /var/log/nginx/access.log \
  --port 3903
Restart=always
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now mtail-nginx
# Test
curl http://localhost:3903/metrics | head -5
```

**Validation:** Verify TCP/3903 and the `http_requests_total` series after generating requests. This parser was transcribed from the lab guide but the mtail program syntax and log permissions must be checked against the installed version; it has not been executed in this package.

## 5. End-to-end checks

```bash
curl -fsS http://10.20.200.10/
curl -fsS http://10.20.200.10:9100/metrics | head
curl -fsS http://10.20.200.10:3903/metrics | head
```

> This server is located on the emulated DMZ, not a public hosting service. Open only the ports needed by the lab on pfSense.
