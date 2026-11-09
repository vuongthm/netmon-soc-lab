# pfSense — firewall, inter-subnet routing, NAT and Suricata sensor

**Role:** central gateway for internal and DMZ segments, ZeroTier ingress and IDS capture point. This setup requires console and WebGUI configuration; it is **not** a paste-ready CLI script.

## 1. Assign interfaces

| pfSense interface | Emulated port | Network | IPv4 |
| --- | --- | --- | --- |
| OPT1 (ZeroTier) | e0 | Overlay | 172.24.0.115/16 |
| WAN | e1 | cloud_nat | DHCP |
| LAN | e2 | Core-Router | 10.20.255.254/24 |
| OPT2 (DMZ1) | e3 | Web / Server02 | 10.20.200.1/24 |
| OPT3 (DMZ2) | e4 | DNS + FTP / Server01 | 10.20.201.1/24 |

On the pfSense console, select **Assign Interfaces (option 1)** and then **Set interface IP addresses (option 2)**. The lab notes specify a ZeroTier peer/hub `172.24.0.200` for OPT1; this is an overlay-specific route and must not accidentally replace the desired WAN default route.

## 2. Reach internal VLANs through Core-Router

In **System → Routing → Gateways**, add:

| Parameter | Value |
| --- | --- |
| Interface | LAN |
| Gateway name | LAN_CORE_ROUTER |
| Next hop | 10.20.255.1 |

In **System → Routing → Static Routes**, add `10.20.0.0/16` via `LAN_CORE_ROUTER`. The attached DMZ interfaces are already connected subnets and retain their more-specific `/24` routes.

## 3. WAN outbound NAT

Under **Firewall → NAT → Outbound**, choose Hybrid mode and add a rule for source `10.20.0.0/16`, outbound interface WAN, translation to WAN address. Check whether DMZ networks require NAT under the active pfSense rules; do not assume the same rule covers them unless deliberately included.

## 4. Firewall access rules (lab only)

The experiment uses permissive rules for LAN, ZeroTier OPT1 and the two DMZ interfaces to simplify measurements. The original console examples are:

```console
easyrule pass opt1 any any any any
easyrule pass lan any any any any
easyrule pass opt2 any any any any
easyrule pass opt3 any any any any
```

These are included **for reference**, not as a recommended secure policy. Validate the CLI syntax on the installed pfSense release or create WebGUI rules explicitly. The equivalent lab intent is to permit the relevant source networks to reach the test destinations. For any non-isolated environment, replace these broad passes with narrowly scoped source, destination and port rules.

## 5. SNMP monitoring

Install/configure the SNMP service in pfSense. The lab records:

| Setting | Value |
| --- | --- |
| Monitoring source | 172.24.0.10/32 |
| pfSense management IP | 172.24.0.115 |
| UDP port | 161 |
| Community (lab only) | public |
| Interface counters | enabled |
| System location | PNETLab |
| System contact | admin@lab.local |

Permit only the monitor IP to UDP/161 on OPT1 (ZeroTier), not on WAN. The implementation notes mention both `bsdsnmpd` and installing `net-snmp`—the service menu and package availability depend on pfSense release and must be checked on the installed system.

From the monitor:

```bash
curl 'http://localhost:9116/snmp?target=172.24.0.115&module=if_mib'
```

The implementation document contains one test using `172.24.0.110`; the topology and Prometheus target consistently identify **`172.24.0.115`** as pfSense. Verify against the live node before deployment.

## 6. Install Suricata

In **System → Package Manager → Available Packages**, install Suricata. Under **Services → Suricata**, create sensor instances for the interfaces that carry the attack simulations. The report describes observation on WAN, DMZ1, DMZ2, LAN and the ZeroTier segment; the screenshot sequence highlights WAN and DMZ setup. Enable EVE JSON alerts for each monitored interface so NetMon SOC can ingest the per-interface log stream.

Load only the selected detection rule profile; see [`Suricata.md`](Suricata.md). Confirm actual interface names, ruleset activation and the generated `eve.json` paths on the installed version.

## 7. Validation checklist

- WAN has a valid default route and Internet access as required for package installation.
- Core-Router `10.20.255.1` is reachable from pfSense LAN.
- Routes to `10.20.10.0/24` through `10.20.40.0/24` resolve via Core-Router.
- Server02 `10.20.200.10` and Server01 `10.20.201.10` are reachable by authorized clients.
- SNMP data can be collected from `172.24.0.10` but is not exposed on WAN.
- Suricata captures on intended interfaces and writes EVE JSON events.

> Static routes, broad ACLs and default test credentials here are specific to a controlled PNETLab lab and are not production security recommendations.
