# NetMon SOC — integration verification checklist

Run checks only after the target node and service are configured. The commands below are observational and do not modify lab state.

## Transport and routing

```bash
for ip in 172.24.0.115 10.20.0.1 10.20.0.2 10.20.0.3 10.20.200.10 10.20.201.10; do
  ping -c 1 -W 2 "$ip" >/dev/null && echo "UP   $ip" || echo "DOWN $ip"
done
```

On Core-Router and both L3 switches, confirm the OSPF adjacencies, routes and interface state using the Cisco CLI (`show ip ospf neighbor`, `show ip route`, `show ip interface brief`). Confirm VLANs 10, 20, 30 and 40 are on their intended access ports.

## Monitor and agents

```bash
sudo systemctl status prometheus snmp_exporter
promtool check config /etc/prometheus/prometheus.yml
curl -fsS http://localhost:9090/-/healthy
curl -fsS 'http://localhost:9116/snmp?target=172.24.0.115&module=if_mib' | grep -m1 ifOperStatus
curl -fsS http://10.20.200.10:9100/metrics | head
curl -fsS http://10.20.201.10:9100/metrics | head
```

Inspect the Prometheus `/api/v1/targets` output for the four SNMP, two Node Exporter and three mtail jobs. Do not assume an optional mtail target is healthy until the corresponding log parser is installed and verified.

## Application-facing services

```bash
curl -fsS http://10.20.200.10/
dig @10.20.201.10 web.lab.local +short
dig @10.20.201.10 ftp.lab.local +short
curl -fsS http://localhost:5000/api/summary
curl -fsS http://localhost:5000/api/devices
```

Expected local DNS results: `web.lab.local` → `10.20.200.10`; `ftp.lab.local` → `10.20.201.10`.

## Security monitoring

- Confirm Suricata is active on the selected pfSense sensor interfaces.
- Confirm an EVE JSON log file is being written and can be read by the collector account.
- Activate **one** Suricata rule profile at a time; verify the rule syntax with the installed engine before test traffic is generated.
- Keep offensive attack-generation scripts separate from the baseline configuration and use them only in an isolated, authorized lab.

**Evidence standard:** a healthy exporter or BGP/OSPF control state by itself does not prove end-to-end service availability. Check the network, application and telemetry layers together.
