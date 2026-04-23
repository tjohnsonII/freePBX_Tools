// OnNet Mikrotik Config Template
export const onNetMikrotikConfigTemplate = `
/interface ethernet
set [ find default-name=ether1 ] comment="WAN"
set [ find default-name=ether2 ] comment="LAN"
/ip address
add address=10.0.0.1/24 interface=ether2
/ip pool
add name=dhcp_pool ranges=10.0.0.10-10.0.0.100
/ip dhcp-server
add address-pool=dhcp_pool disabled=no interface=ether2 name=dhcp1
/ip dhcp-server network
add address=10.0.0.0/24 dns-server=8.8.8.8,1.1.1.1 gateway=10.0.0.1 netmask=24
`;
