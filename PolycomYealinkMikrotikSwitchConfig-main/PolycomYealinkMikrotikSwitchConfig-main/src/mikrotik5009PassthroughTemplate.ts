// Mikrotik 5009 Passthrough template
export const mikrotik5009Passthrough = `
/interface ethernet
set [ find default-name=ether1 ] comment="WAN"
set [ find default-name=ether2 ] comment="LAN"
/ip address
add address=192.168.88.2/24 interface=ether2
/ip route
add distance=1 gateway=192.168.88.1
`;
