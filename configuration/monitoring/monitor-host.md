# Monitoring host — Prometheus and SNMP Exporter

**Host:** `172.24.0.10` on the lab's ZeroTier overlay.  
**Purpose:** collect infrastructure metrics for NetMon SOC.  
**Versions referenced in the implementation notes:** Prometheus `2.49.0`, SNMP Exporter `0.24.1`. Validate their availability and compatibility with your installation; they are **lab version references**, not a claim of latest releases.

## Service addresses

| Service | Lab endpoint |
| --- | --- |
| Prometheus | `http://172.24.0.10:9090` |
| SNMP Exporter | `http://172.24.0.10:9116` |
| Flask / NetMon SOC | `http://172.24.0.10:5000` |
| PNETLab web host (different machine) | `http://172.24.0.100` |
| pfSense WebGUI | `https://172.24.0.115` |

## 1. Install the exporters and Prometheus

This guide mirrors the recorded Debian/Ubuntu lab deployment. Check the archive URL and integrity, account existence and compatibility before running commands on a real machine.

### SNMP Exporter

```bash
sudo apt update
sudo apt install -y snmp
wget https://github.com/prometheus/snmp_exporter/releases/download/v0.24.1/snmp_exporter-0.24.1.linux-amd64.tar.gz
tar xzf snmp_exporter-0.24.1.linux-amd64.tar.gz
sudo install -m 0755 snmp_exporter-0.24.1.linux-amd64/snmp_exporter /usr/local/bin/snmp_exporter
sudo mkdir -p /etc/snmp_exporter
sudo install -m 0644 snmp_exporter-0.24.1.linux-amd64/snmp.yml /etc/snmp_exporter/snmp.yml
```

The exporter must provide an `if_mib` module that matches the monitoring profile. **Check its configuration** and ensure the device's SNMPv2c credentials match the module; reaching port 9116 does not by itself guarantee successful scraping.

Create `/etc/systemd/system/snmp_exporter.service`:

```ini
[Unit]
Description=SNMP Exporter
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/local/bin/snmp_exporter --config.file=/etc/snmp_exporter/snmp.yml --web.listen-address=127.0.0.1:9116
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

The local-only listener is sufficient because Prometheus in this lab calls `localhost:9116`. Bind to another interface only after defining appropriate access controls.

### Prometheus

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin prometheus 2>/dev/null || true
sudo mkdir -p /etc/prometheus /var/lib/prometheus
wget https://github.com/prometheus/prometheus/releases/download/v2.49.0/prometheus-2.49.0.linux-amd64.tar.gz
tar xzf prometheus-2.49.0.linux-amd64.tar.gz
sudo install -m 0755 prometheus-2.49.0.linux-amd64/prometheus /usr/local/bin/prometheus
sudo install -m 0755 prometheus-2.49.0.linux-amd64/promtool /usr/local/bin/promtool
sudo chown -R prometheus:prometheus /var/lib/prometheus
```

## 2. Deploy the canonical configuration

The **only maintained scrape YAML in this repository** is [`../../source/code/prometheus.yml`](../../source/code/prometheus.yml). From the repository root, install it on the monitoring machine:

```bash
sudo install -m 0644 source/code/prometheus.yml /etc/prometheus/prometheus.yml
promtool check config /etc/prometheus/prometheus.yml
```

There are **nine scrape jobs**: four SNMP targets (pfSense, Core-Router, SwL3A, SwL3B), two Node Exporter endpoints (Server01 and Server02), and three **optional** mtail exporters (Nginx, DNS, FTP). These are **six monitored devices**, not nine devices.

Create `/etc/systemd/system/prometheus.service`:

```ini
[Unit]
Description=Prometheus
After=network-online.target
Wants=network-online.target

[Service]
User=prometheus
ExecStart=/usr/local/bin/prometheus --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/var/lib/prometheus --storage.tsdb.retention.time=30d --web.listen-address=127.0.0.1:9090
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

For remote authorized access to the Prometheus UI, use a secured reverse proxy or explicitly bind to a permitted interface and enforce network restrictions. The historical lab exposed the UI at `172.24.0.10:9090`; a loopback-only unit does **not** expose that address directly.

Start services:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now snmp_exporter prometheus
sudo systemctl status snmp_exporter prometheus
```

## 3. Verify collection

```bash
curl -fsS http://127.0.0.1:9090/-/healthy
curl -fsS 'http://127.0.0.1:9116/snmp?target=172.24.0.115&module=if_mib' | head
curl -fsS http://127.0.0.1:9090/api/v1/targets | python3 -m json.tool
```

If you edit the YAML, validate it with `promtool` and restart Prometheus. Check individual scrape errors in the Targets UI or API: SNMP connectivity (UDP/161), credentials, exporter module, Node Exporter TCP/9100 and routing to `10.20.0.0/16` are distinct prerequisites.

**Do not treat optional mtail targets as guaranteed UP.** The log parser must exist, read the right service log and expose the expected port on the respective server. See [`../servers/Server01-DNS-FTP.md`](../servers/Server01-DNS-FTP.md) and [`../servers/Server02-Web.md`](../servers/Server02-Web.md) for the recorded service procedures.

## Security boundary

The lab material uses SNMPv2c and sample community `public`. Restrict management traffic to the isolated overlay and prefer authenticated/encrypted polling (e.g. SNMPv3) for real networks. This document has not been live-tested against the imported PNETLab images.
