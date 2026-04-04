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
        <textarea value={mikrotik5009Bridge} readOnly rows={10} className="mikrotik-textarea" aria-label="5009 Bridge template" />
        <h3>5009 Passthrough</h3>
        <textarea value={mikrotik5009Passthrough} readOnly rows={10} className="mikrotik-textarea" aria-label="5009 Passthrough template" />
        <h3>OnNet Config</h3>
        <textarea value={onNetMikrotikConfigTemplate} readOnly rows={10} className="mikrotik-textarea" aria-label="OnNet Config template" />
        <h3>OTT Template (Editable)</h3>
        <div className="mikrotik-form-row">
          <label className="mikrotik-label">
            IP
            <input name="ip" value={ottFields.ip} onChange={handleOttField} placeholder="XXX.XXX.XXX.XXX" className="mikrotik-input" title="Customer IP address" />
          </label>
          <label className="mikrotik-label">
            Customer Name
            <input name="customerName" value={ottFields.customerName} onChange={handleOttField} placeholder="CUSTOMER NAME" className="mikrotik-input" title="Customer name" />
          </label>
          <label className="mikrotik-label">
            Customer Address
            <input name="customerAddress" value={ottFields.customerAddress} onChange={handleOttField} placeholder="CUSTOMER ADDRESS" className="mikrotik-input" title="Customer address" />
          </label>
          <label className="mikrotik-label">
            City
            <input name="city" value={ottFields.city} onChange={handleOttField} placeholder="CITY" className="mikrotik-input" title="City" />
          </label>
          <label className="mikrotik-label">
            XIP
            <input name="xip" value={ottFields.xip} onChange={handleOttField} placeholder="XIP" className="mikrotik-input" title="XIP value" />
          </label>
          <label className="mikrotik-label">
            Handle
            {scraperHandles.length > 0 ? (
              <select
                name="handle"
                value={ottFields.handle}
                onChange={handleOttField}
                className="mikrotik-input"
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
              <input name="handle" value={ottFields.handle} onChange={handleOttField} placeholder="HANDLE-CUSTOMERADDRESS" className="mikrotik-input" title="Handle" />
            )}
          </label>
          {scraperOnline !== null && (
            <span className={`mikrotik-status ${scraperOnline ? 'online' : 'offline'}`}>
              {scraperOnline ? '● scraper connected' : '○ scraper offline'}
            </span>
          )}
        </div>
        <textarea value={getOttTemplate(ottFields)} readOnly rows={10} className="mikrotik-textarea" aria-label="OTT template output" />
        <h3>Standalone ATA</h3>
        <textarea value={mikrotikStandAloneATATemplate} readOnly rows={10} className="mikrotik-textarea" aria-label="Standalone ATA template" />
        <h3>DHCP Options</h3>
        <textarea value={mikrotikDhcpOptions} readOnly rows={10} className="mikrotik-textarea" aria-label="DHCP Options template" />
      </div>
    </div>
  );
}