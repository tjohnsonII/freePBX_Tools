// Mikrotik DHCP Options template
export const mikrotikDhcpOptions = `
/ip dhcp-server option
add code=2 name="GMT Offset -5" value=0xFFFFB9B0
add code=42 name=NTP value="'184.105.182.16'"
add code=160 name=prov_160 value="'http://provisioner.123.net'"
add code=66 name=prov_66 value="'http://provisioner.123.net'"
add code=202 name=Phone_vlan value="'VLAN-A=202'"
/ip dhcp-server option sets
add name=Phones_Options options="GMT Offset -5,NTP,prov_66,prov_160,Phone_vlan"
`;
