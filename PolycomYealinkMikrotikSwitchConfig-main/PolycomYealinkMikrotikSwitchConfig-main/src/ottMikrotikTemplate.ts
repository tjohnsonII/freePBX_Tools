// OTT Mikrotik Template with placeholders for user editing
export const ottMikrotikTemplate = `
/interface ethernet
set [ find default-name=ether1 ] comment="WAN"
set [ find default-name=ether2 ] comment="LAN"
# Customer: "CUSTOMER NAME"
# Address: "CUSTOMER ADDRESS"
# City: "CITY"
# XIP: "XIP"
# Handle: "HANDLE-CUSTOMERADDRESS"
/ip address
add address=XXX.XXX.XXX.XXX/24 interface=ether2
`;
