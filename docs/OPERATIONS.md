# Operations

## Prerequisites
- Windows 10/11 with Docker Desktop and Linux container mode.
- PowerShell 7 recommended.
- Cisco SNA Manager, Flow Collector, and Flow Sensor reachable in the lab.
- Confirm Docker subnet does not overlap local, VPN, or SNA networks.

## Read-only discovery
Run in PowerShell:

```powershell
docker version
docker info
docker context ls
docker network ls
Get-NetRoute -AddressFamily IPv4 |
  Sort-Object DestinationPrefix |
  Format-Table DestinationPrefix, NextHop, InterfaceAlias
```

Hyper-V-only discovery (will not identify VMware, VirtualBox, Proxmox, or other hypervisors):

```powershell
Get-VMSwitch | Format-Table Name, SwitchType, NetAdapterInterfaceDescription
```

## Isolated identity test only
After checking for subnet conflicts, create a private Docker network:

```powershell
docker network create --driver bridge --internal --subnet 172.30.50.0/24 sna-lab
```

Create 50 idle hosts:

```powershell
docker pull alpine:3.21
1..50 | ForEach-Object {
  $n = $_
  $ip = "172.30.50.$($n + 10)"
  $name = "sna-host-{0:D3}" -f $n
  docker run -d --name $name --hostname $name --network sna-lab --ip $ip --memory 128m --cpus 0.25 --restart unless-stopped alpine:3.21 sleep infinity
}
```

Verify:

```powershell
docker ps --filter "name=sna-host"
docker network inspect sna-lab
1..50 | ForEach-Object {
  $name = "sna-host-{0:D3}" -f $_
  docker inspect --format "{{.Name}} {{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}" $name
}
```

This validates container lifecycle and internal IP assignment only. It does not generate traffic, provide externally routable source addresses, or prove SNA visibility.

Cleanup:

```powershell
1..50 | ForEach-Object {
  $name = "sna-host-{0:D3}" -f $_
  docker rm -f $name
}
docker network rm sna-lab
```

Do not attach traffic workers to external networks or run experiments until the application-level allowlist, hard limits, and stop controls are implemented and verified.