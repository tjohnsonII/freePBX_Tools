import React from 'react';
import { mikrotik5009Bridge } from '../mikrotik5009BridgeTemplate';
import { mikrotik5009Passthrough } from '../mikrotik5009PassthroughTemplate';
import { onNetMikrotikConfigTemplate } from '../onNetMikrotikConfigTemplate';
import { mikrotikStandAloneATATemplate } from '../mikrotikStandAloneATATemplate';
import { mikrotikDhcpOptions } from '../mikrotikDhcpOptionsTemplate';

interface OttFields {
  ip: string;
  customerName: string;
  customerAddress: string;
  city: string;
  xip: string;
  handle: string;
}

interface MikrotikTabProps {
  ottFields: OttFields;
  setOttFields: React.Dispatch<React.SetStateAction<OttFields>>;
  getOttTemplate: (fields: OttFields) => string;
  scraperHandles: { handle: string; name: string; ip: string }[];
  scraperOnline: boolean | null;
}

export default function MikrotikTab({ ottFields, setOttFields, getOttTemplate, scraperHandles, scraperOnline }: MikrotikTabProps) {
  function handleOttField(e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) {
    setOttFields(f => ({ ...f, [e.target.name]: e.target.value }));
  }

  return (
    <div>
      <h2>Mikrotik Templates</h2>
      <div>
        <h3>5009 Bridge</h3>
        <textarea value={mikrotik5009Bridge} readOnly rows={10} style={{ width: '100%' }} aria-label="5009 Bridge template" />
        <h3>5009 Passthrough</h3>
        <textarea value={mikrotik5009Passthrough} readOnly rows={10} style={{ width: '100%' }} aria-label="5009 Passthrough template" />
        <h3>OnNet Config</h3>
        <textarea value={onNetMikrotikConfigTemplate} readOnly rows={10} style={{ width: '100%' }} aria-label="OnNet Config template" />
        <h3>OTT Template (Editable)</h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
            IP
            <input name="ip" value={ottFields.ip} onChange={handleOttField} placeholder="XXX.XXX.XXX.XXX" style={{ padding: '3px 6px' }} title="Customer IP address" />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
            Customer Name
            <input name="customerName" value={ottFields.customerName} onChange={handleOttField} placeholder="CUSTOMER NAME" style={{ padding: '3px 6px' }} title="Customer name" />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
            Customer Address
            <input name="customerAddress" value={ottFields.customerAddress} onChange={handleOttField} placeholder="CUSTOMER ADDRESS" style={{ padding: '3px 6px' }} title="Customer address" />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
            City
            <input name="city" value={ottFields.city} onChange={handleOttField} placeholder="CITY" style={{ padding: '3px 6px' }} title="City" />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
            XIP
            <input name="xip" value={ottFields.xip} onChange={handleOttField} placeholder="XIP" style={{ padding: '3px 6px' }} title="XIP value" />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
            Handle
            {scraperHandles.length > 0 ? (
              <select
                name="handle"
                value={ottFields.handle}
                onChange={handleOttField}
                style={{ padding: '3px 6px' }}
                title="Select handle"
                aria-label="Select handle"
                disabled={!scraperOnline}
              >
                <option value="">— select handle —</option>
                {scraperHandles.map(h => (
                  <option key={h.handle} value={h.handle}>{h.handle} — {h.name}</option>
                ))}
              </select>
            ) : (
              <input name="handle" value={ottFields.handle} onChange={handleOttField} placeholder="HANDLE-CUSTOMERADDRESS" style={{ padding: '3px 6px' }} title="Handle" />
            )}
          </label>
          {scraperOnline !== null && (
            <span style={{ fontSize: 12, alignSelf: 'flex-end', color: scraperOnline ? '#16794a' : '#b42318', paddingBottom: 4 }}>
              {scraperOnline ? '● scraper connected' : '○ scraper offline'}
            </span>
          )}
        </div>
        <textarea value={getOttTemplate(ottFields)} readOnly rows={10} style={{ width: '100%' }} aria-label="OTT template output" />
        <h3>Standalone ATA</h3>
        <textarea value={mikrotikStandAloneATATemplate} readOnly rows={10} style={{ width: '100%' }} aria-label="Standalone ATA template" />
        <h3>DHCP Options</h3>
        <textarea value={mikrotikDhcpOptions} readOnly rows={10} style={{ width: '100%' }} aria-label="DHCP Options template" />
      </div>
    </div>
  );
}