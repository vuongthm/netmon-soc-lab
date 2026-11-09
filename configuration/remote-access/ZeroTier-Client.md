# ZeroTier administration — reach the lab from an external workstation

The lab uses the overlay gateway `172.24.0.115` (pfSense OPT1) to access the internal emulated `10.20.0.0/16` network. The following steps configure the **client workstation**, not pfSense itself.

## Linux — immediate route

Find the local ZeroTier interface name first (`ip -br link`); the recorded lab device was `ztxoonzdie`.

```bash
sudo ip route add 10.20.0.0/16 via 172.24.0.115 dev ztxoonzdie
ip route get 10.20.200.10
```

## Linux — persistent systemd route

Create `/etc/systemd/system/zerotier-routes.service`:

```ini
[Unit]
Description=ZeroTier Static Routes
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStartPre=/bin/bash -c 'for i in {1..10}; do ip link show ztxoonzdie && exit 0; sleep 2; done; exit 1'
ExecStart=/usr/sbin/ip route replace 10.20.0.0/16 via 172.24.0.115 dev ztxoonzdie
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now zerotier-routes
ip route | grep 10.20
```

Replace `ztxoonzdie` if the actual overlay interface differs.

## Windows — elevated Command Prompt or PowerShell

```powershell
ipconfig | findstr /i "zerotier"
route -p add 10.20.0.0 mask 255.255.0.0 172.24.0.115 metric 10
route print | findstr "10.20"
```

The machine must be authorized in the overlay and allowed through the pfSense policy. Only use these routes while connected to the lab overlay.
