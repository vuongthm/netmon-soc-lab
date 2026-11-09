# Infrastructure configuration

This directory contains the deployment material for the **NetMon SOC PNETLab lab**. It is organized by **device** and **role**, not by the chapter numbers of any report.

- `.txt` files are complete Cisco CLI blocks intended for the matching emulated device (subject to image compatibility).
- `.md` files are multi-stage procedures involving interfaces, host files, services, credentials, and validation.
- Suricata custom signatures remain separate text files and **must not be activated as overlapping profiles**.

## Network and address plan

| Node / segment | Address | Purpose |
| --- | --- | --- |
| Monitor / application host | `172.24.0.10` | Prometheus, SNMP Exporter, Flask/PostgreSQL |
| pfSense ZeroTier (OPT1) | `172.24.0.115/16` | Remote access, telemetry, EVE JSON over SSH |
| pfSense LAN ↔ Core-Router | `10.20.255.254/24` ↔ `10.20.255.1/24` | Routed internal link |
| Core-Router loopback | `10.20.0.1/32` | SNMP/management target |
| SwL3A loopback | `10.20.0.2/32` | SNMP/management target |
| SwL3B loopback | `10.20.0.3/32` | SNMP/management target |
| VLAN 10 — IT | `10.20.10.0/24` | SwL3A gateway `.1` |
| VLAN 20 — Sales | `10.20.20.0/24` | SwL3A gateway `.1` |
| VLAN 30 — HR | `10.20.30.0/24` | SwL3B gateway `.1` |
| VLAN 40 — Engineering | `10.20.40.0/24` | SwL3B gateway `.1` |
| Server02, Web DMZ | `10.20.200.10/24` | Nginx; pfSense `.1` gateway |
| Server01, DNS/FTP DMZ | `10.20.201.10/24` | BIND9 and vsftpd; pfSense `.1` gateway |

The monitor host is **`172.24.0.10`**. The separate `172.24.0.100` address in the implementation notes identifies the PNETLab web host, **not** the monitor. pfSense is `172.24.0.115`; an isolated example using `172.24.0.110` was inconsistent with the address plan.

## Configuration index

| Component | File | Apply on |
| --- | --- | --- |
| Core-Router | [`network/Core-Router.txt`](network/Core-Router.txt) | Cisco IOSv router |
| SwL3A / SwL3B | [`network/SwitchL3A.txt`](network/SwitchL3A.txt), [`network/SwitchL3B.txt`](network/SwitchL3B.txt) | Cisco Layer 3 switches |
| AccessA1 / A2 / B1 / B2 | [`network/`](network/) | Four Cisco access switches |
| pfSense routing, NAT, SNMP | [`firewall/pfSense.md`](firewall/pfSense.md) | pfSense console and WebGUI |
| Suricata sensors and rules | [`firewall/Suricata.md`](firewall/Suricata.md) | pfSense Suricata package |
| Server01 (DNS + FTP) | [`servers/Server01-DNS-FTP.md`](servers/Server01-DNS-FTP.md) | Ubuntu host at `10.20.201.10` |
| Server02 (Web) | [`servers/Server02-Web.md`](servers/Server02-Web.md) | Ubuntu host at `10.20.200.10` |
| Prometheus + SNMP Exporter | [`monitoring/monitor-host.md`](monitoring/monitor-host.md) | Monitor host at `172.24.0.10` |
| Flask/NetMon SOC integration | [`monitoring/NetMon-SOC-App.md`](monitoring/NetMon-SOC-App.md) | Application in [`../source/code/`](../source/code/README.md) |
| ZeroTier client routes | [`remote-access/ZeroTier-Client.md`](remote-access/ZeroTier-Client.md) | Authorized administrator workstation |
| Integration checks | [`verification.md`](verification.md) | Monitor plus device CLIs |

## Recommended deployment sequence

1. **Build the lab:** import the correct node images, connect pfSense, router, switches, VLAN access nodes, DMZ servers, and the monitoring host. Verify interface names against the image before pasting any CLI.
2. **Establish routing:** configure pfSense interfaces, internal routes, selective firewall rules, Core-Router OSPF, and SwL3A/B VLAN/DHCP. Add access switch configurations. Check reachable gateways before proceeding.
3. **Start services:** configure Server01 BIND9/vsftpd and Server02 Nginx, plus exporters. Validate DNS records and HTTP from the permitted monitoring path.
4. **Collect metrics:** install SNMP Exporter and Prometheus on the monitor. Copy **[`../source/code/prometheus.yml`](../source/code/prometheus.yml)** to `/etc/prometheus/prometheus.yml` and run `promtool check config`. There are **four SNMP**, **two Node Exporter**, and **three optional mtail** scrape jobs.
5. **Enable IDS:** configure Suricata on the intended pfSense interfaces. Select **one** rule profile, validate it with the installed engine, and verify the EVE JSON files before enabling the SSH collector.
6. **Start the application:** use the actual files in **[`../source/code/`](../source/code/README.md)**; configure `.env` locally, PostgreSQL, and any Telegram/Groq integrations.
7. **Verify end-to-end:** follow [`verification.md`](verification.md); preserve baseline observations before generating test traffic.

## Configuration ownership and consistency

**Canonical runtime files:**

- Prometheus scrape jobs: **`source/code/prometheus.yml`** (the file to deploy); `monitoring/monitor-host.md` explains installation and checks but does not maintain a second copy.
- Device inventory, alert thresholds, source-specific EVE paths: **`source/code/config.py`**. Modify this file for actual changes to the application's registry.
- Flask dependencies: **`source/code/requirements.txt`**.
- Application logic/API: **`source/code/app.py`, `routes/`, `services/`, and `database/`**.

The Cisco `.txt` files, pfSense WebGUI steps, and server procedures document the network configuration; they are **not automatically applied** by the Flask application. Some commands and release-version specifics may depend on the imported appliance image. The lab's CLI configurations and custom IDS signatures have **not been executed or engine-validated during this documentation update**.

## Known deployment caveats

- Sample `enable secret`, community strings, FTP credentials, and broad pfSense access rules are for an **isolated lab only**. Restrict access and replace all lab credentials before exposing any service.
- The installed SNMP Exporter must include the `if_mib` module expected by the Prometheus jobs. Validate module presence and metrics before declaring a job healthy.
- Three Suricata signature files contain overlapping SIDs. **Do not activate them simultaneously.** See [`firewall/Suricata.md`](firewall/Suricata.md).
- Suricata writes EVE JSON to **per-interface** paths on pfSense; confirm them with `find /var/log/suricata -name eve.json`, then compare with `source/code/config.py`.
- Optional mtail jobs depend on the actual log location, parser syntax, and running service. Their presence in YAML does not prove availability.
- The supplied `scripts/setup_db.sh` can modify PostgreSQL settings and package-management state. Review it carefully; manual provisioning steps are provided in the [application README](../source/code/README.md).

This documentation describes a **reproducible lab design**, not a certified one-command installation or a production-hardened SOC.
