# Suricata — custom IDS rule profiles

The NetMon SOC lab uses Suricata as a **passive detection system** on pfSense. Sensor logs are collected in EVE JSON for the SOC view. Three profiles are preserved because they appeared in the implementation notes:

| Profile | Rules | Role |
| --- | ---: | --- |
| `rules/primary-lab-rule-set.txt` | 41 | Combined WAN, Web, FTP and DNS scenarios |
| `rules/alternatives/web-legacy-rules.txt` | 9 | Earlier web-only rule set |
| `rules/alternatives/ftp-dns-legacy-rules.txt` | 20 | Earlier FTP/DNS rule set |

**Do not enable all three profiles together.** They reuse SIDs and some patterns differ between revisions. Start with the **41-rule** consolidated profile, check the signatures against the Suricata version installed on pfSense, and activate only the needed rules for the sensor interfaces. Alternatives are kept for historical comparison, not as concurrent configuration.

## Deployment through pfSense WebGUI

1. Install the Suricata package through the pfSense Package Manager.
2. Create/edit the Suricata interface instance in **Services → Suricata → Interfaces**.
3. Enable EVE JSON alert logging and the desired protocol logging options.
4. Add the selected `alert ...` signatures to the local **Custom Rules** interface or the equivalent ruleset facility supported by the installed package.
5. Save, validate/reload, and confirm the interface instance is running.
6. Monitor the per-interface `eve.json` alert stream; confirm the NetMon SOC ingestion job can read it via the configured SSH path.

## Audit before use

- All rules are reproduced without rewriting the rule conditions; no in-environment Suricata syntax test was available while packaging.
- Matching behavior depends on signature buffers, threshold modes, network placement and Suricata version.
- WAN-targeted signatures contain the lab address `172.24.0.115` used for overlay management. Confirm the real traffic direction seen by the selected sensor interface.
- These are detection rules, **not** attack-generation scripts. Source names and IPs are from the isolated test topology.
- Do not expose the lab's permissive firewall rules or SNMPv2c community to the public Internet.
