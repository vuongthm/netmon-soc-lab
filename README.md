# NetMon SOC Lab

**Network monitoring, intrusion detection, and anomaly analysis in an emulated enterprise network.**

NetMon SOC is a research and implementation project combining **network observability** and **security-event monitoring** in a PNETLab topology. It collects infrastructure metrics, ingests Suricata IDS alerts, applies Isolation Forest models to selected measurements, manages alert lifecycles, and provides a Flask dashboard with Telegram notifications and an optional Groq-powered assistant.

**Authors:** Trần Hoàng Minh Vương · Diệp Mạnh Tuấn  
**Environment:** PNETLab · isolated network lab  
**Project year:** 2026

## What the project demonstrates

- **Connectivity and segmentation:** pfSense firewall/gateway, Cisco IOSv routing with OSPF, two Layer 3 switches, four access switches, four user VLANs, and two service DMZs.
- **Infrastructure visibility:** Prometheus scrapes four network-device jobs through SNMP Exporter and two Ubuntu servers through Node Exporter at a configured **15-second interval**.
- **Security monitoring:** Suricata on pfSense produces EVE JSON alerts. The application retrieves alerts over SSH and organizes them by source interface and security zone.
- **Event handling:** PostgreSQL stores alerts and IDS events. The Flask application presents dashboards, service checks, alert management, and a SOC view.
- **Anomaly analysis:** seven Isolation Forest model artifacts and training materials are included. The runtime's model loader and anomaly scan are implemented in the application source.
- **Operator assistance:** Telegram delivers selected notifications; an optional Groq integration uses monitoring context to answer operator questions.

These are functions and configurations in a **lab proof-of-concept**, not claims of production readiness, independently measured accuracy, or guaranteed detection of every attack class.

## Architecture at a glance

```text
                   Monitoring host (172.24.0.10)
             Prometheus + SNMP Exporter + Flask + DB
                           | ZeroTier
                    pfSense (172.24.0.115)
                   /        |          \
           Core-Router   Server02      Server01
              |          DMZ Web       DMZ DNS/FTP
         +----+----+
       SwL3A     SwL3B
       /   \      /   \
    VLAN10 20  VLAN30 40

Sources -> exporters / Suricata -> collection -> PostgreSQL / Prometheus
                                     -> dashboards / alerts / AI analysis
```

The diagram is conceptual; use the [configuration address plan](configuration/README.md#network-and-address-plan) for exact interfaces and routes.

## Repository layout

| Directory | Purpose |
| --- | --- |
| [`configuration/`](configuration/README.md) | Paste-ready Cisco CLI, step-by-step pfSense/Linux setup, Suricata rule profiles, and verification. |
| [`source/code/`](source/code/README.md) | **Complete supplied Flask application source**, templates, services, database code, dependencies, and the Prometheus YAML. |
| [`source/machine-learning/`](source/machine-learning/README.md) | Training notebook, historical metrics data, and seven serialized model artifacts. |
| [`report/`](report/README.md) | **Both completed project reports**, in Vietnamese and English. |

The application source and both PDF reports are **already included**; these are not future placeholders.

## Read the project

- [Vietnamese report](report/NetMon_SOC_VI.docx.pdf)
- [English report](report/NetMon_SOC_EN.docx.pdf)
- [Application installation and API documentation](source/code/README.md)
- [Network and service configuration](configuration/README.md)
- [Non-destructive verification checklist](configuration/verification.md)
- [Machine-learning artifacts and caveats](source/machine-learning/README.md)

## Quick start: choose the right entry point

1. Read the [network plan and deployment order](configuration/README.md). Build the **isolated** PNETLab topology before expecting any host IP to respond.
2. Configure the Cisco/pfSense devices and both servers using the documents in `configuration/`.
3. Deploy Prometheus/SNMP Exporter according to the [monitor-host guide](configuration/monitoring/monitor-host.md). Use **[`source/code/prometheus.yml`](source/code/prometheus.yml)** as the canonical scrape configuration.
4. Set up PostgreSQL, a Python environment, and local secrets as described in [the application README](source/code/README.md). Launch Flask from `source/code/`.
5. Validate the system with [`configuration/verification.md`](configuration/verification.md) before performing any test traffic.

## Technologies

`PNETLab` · `Cisco IOSv / OSPF / VLAN / DHCP` · `pfSense` · `ZeroTier` · `Suricata / EVE JSON` · `Prometheus / SNMP Exporter / Node Exporter` · `Flask` · `PostgreSQL / SQLAlchemy` · `Isolation Forest / scikit-learn` · `Telegram Bot API` · `Groq LLM`

## Scope, security, and validation

The VLAN/IP addressing and device labels describe the **emulated environment**, not an operational corporate network. Configuration examples contain lab-only settings such as SNMPv2c `public`, permissive firewall rules, and sample credentials; **never publish a reachable lab or reuse these settings in production**. Keep `.env`, keys, and real tokens private.

The repository contains real application code and artifacts, but the project has **not been re-deployed or end-to-end validated as part of this documentation refresh**. Evaluate platform-specific Cisco syntax, Suricata signatures, exporter compatibility, and network reachability in your own authorized environment. Serialized `.pkl` models must only be loaded when their origin is trusted.
