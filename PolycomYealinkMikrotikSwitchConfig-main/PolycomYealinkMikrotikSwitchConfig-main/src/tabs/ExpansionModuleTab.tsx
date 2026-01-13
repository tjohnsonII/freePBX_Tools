import React, { useState } from 'react';
// Expansion module preview icons, tooltips, and Polycom constants
import { EXP_TYPE_ICONS, EXP_TYPE_TOOLTIPS, POLYCOM_PAGE_LABELS, POLYCOM_KEYS_PER_PAGE } from '../constants/expansionModule'; // POLYCOM_PAGE_LABELS, POLYCOM_KEYS_PER_PAGE are used in Polycom preview
// ...import any other shared components or icons as needed

// Polycom expansion module state shape
interface PolycomSection {
  address: string;         // SIP address or extension for the key
  label: string;           // Display label for the key
  type: string;            // Key function type (e.g., automata for BLF)
  linekeyCategory: string; // Key category (BLF, EFK, etc.)
  linekeyIndex: string;    // Key position (1-84)
  activePage: number;      // Current preview page (0-2)
}

// Main Expansion Module Tab component
const ExpansionModuleTab: React.FC = () => {
  // Polycom expansion module form state
  const [polycomSection, setPolycomSection] = useState<PolycomSection>({
    address: '',
    label: '',
    type: 'automata',
    linekeyCategory: 'BLF',
    linekeyIndex: '',
    activePage: 0,
  });
  // Polycom config output
  const [polycomOutput, setPolycomOutput] = useState('');

  // Yealink expansion module form state
  const [yealinkSection, setYealinkSection] = useState({
    templateType: 'BLF',   // BLF or SpeedDial
    sidecarPage: '1',      // Page number (1-3)
    sidecarLine: '1',      // Button number (1-20)
    label: '',             // Display label
    value: '',             // Extension or number
    pbxIp: '',             // PBX IP for BLF
  });
  // Yealink config output
  const [yealinkOutput, setYealinkOutput] = useState('');

  // Generate Yealink expansion config string based on form state
  const generateYealinkExpansion = () => {
    const { templateType, sidecarPage, sidecarLine, value, pbxIp } = yealinkSection;
    let config = '';
    if (templateType === 'BLF') {
      config += `expansion_module.${sidecarPage}.key.${sidecarLine}.type=16\n`;
      config += `expansion_module.${sidecarPage}.key.${sidecarLine}.value=${value}@${pbxIp}\n`;
      config += `expansion_module.${sidecarPage}.key.${sidecarLine}.line=1\n`;
    } else {
      config += `expansion_module.${sidecarPage}.key.${sidecarLine}.type=13\n`;
      config += `expansion_module.${sidecarPage}.key.${sidecarLine}.value=${value}\n`;
      config += `expansion_module.${sidecarPage}.key.${sidecarLine}.line=1\n`;
    }
    setYealinkOutput(config);
  };

  // Generate Polycom expansion config string based on form state
  const generatePolycomExpansion = () => {
    const { address, label, type, linekeyCategory, linekeyIndex } = polycomSection;
    let config = '';
    config += `attendant.resourcelist.${linekeyIndex}.address=${address}\n`;
    config += `attendant.resourcelist.${linekeyIndex}.label=${label}\n`;
    config += `attendant.resourcelist.${linekeyIndex}.type=${type}\n`;
    config += `linekey.${linekeyIndex}.category=${linekeyCategory}\n`;
    config += `linekey.${linekeyIndex}.index=${linekeyIndex}\n`;
    setPolycomOutput(config);
  };

  return (
    <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap' }}>
      {/* Yealink Expansion Module Preview and Form */}
      <div style={{ flex: 1, minWidth: 320 }}>
        <h3>Yealink Expansion Module</h3>
        {/* Device images for user reference */}
        <img src="/expansion/yealinkexp40.jpeg" alt="Yealink EXP40" style={{ width: '100%', maxWidth: 260, marginBottom: 8, borderRadius: 8, border: '1px solid #ccc' }} />
        <img src="/expansion/yealinkexp50.jpeg" alt="Yealink EXP50" style={{ width: '100%', maxWidth: 260, marginBottom: 8, borderRadius: 8, border: '1px solid #ccc' }} />
        {/* Instructions for users */}
        <div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 12, margin: '16px 0' }}>
          <b>Instructions:</b> Fill out the form below to generate a config for a Yealink expansion key. Use the page toggles to preview each page. Hover over any key in the preview for details.
        </div>
        {/* Yealink config form */}
        <div className="form-group" style={{ marginBottom: 16 }}>
          <label>Template Type:
            <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title="BLF: Busy Lamp Field (monitors extension/park status). SpeedDial: Quick dial to a number or extension.">ℹ️</span>
          </label>
          <select value={yealinkSection.templateType} onChange={e => setYealinkSection(s => ({ ...s, templateType: e.target.value }))}>
            <option value="BLF">BLF</option>
            <option value="SpeedDial">SpeedDial</option>
          </select>
        </div>
        <div className="form-group" style={{ marginBottom: 16 }}>
          <label>Sidecar Page (1-3):
            <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title="Select which page of the expansion module to configure (1-3).">ℹ️</span>
          </label>
          <input type="number" min="1" max="3" value={yealinkSection.sidecarPage} onChange={e => setYealinkSection(s => ({ ...s, sidecarPage: e.target.value }))} />
        </div>
        <div className="form-group" style={{ marginBottom: 16 }}>
          <label>Sidecar Line (1-20):
            <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title="Select which button (1-20) on the current page to configure.">ℹ️</span>
          </label>
          <input type="number" min="1" max="20" value={yealinkSection.sidecarLine} onChange={e => setYealinkSection(s => ({ ...s, sidecarLine: e.target.value }))} />
        </div>
        <div className="form-group" style={{ marginBottom: 16 }}>
          <label>Label:
            <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title="The text label that will appear on the phone's display for this key.">ℹ️</span>
          </label>
          <input type="text" value={yealinkSection.label} onChange={e => setYealinkSection(s => ({ ...s, label: e.target.value }))} />
        </div>
        <div className="form-group" style={{ marginBottom: 16 }}>
          <label>Value (Phone/Ext):
            <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title="The extension or number this key will dial or monitor.">ℹ️</span>
          </label>
          <input type="text" value={yealinkSection.value} onChange={e => setYealinkSection(s => ({ ...s, value: e.target.value }))} />
        </div>
        {/* PBX IP only shown for BLF type */}
        {yealinkSection.templateType === 'BLF' && (
          <div className="form-group" style={{ marginBottom: 16 }}>
            <label>PBX IP:
              <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title="The PBX IP address for BLF monitoring.">ℹ️</span>
            </label>
            <input type="text" value={yealinkSection.pbxIp} onChange={e => setYealinkSection(s => ({ ...s, pbxIp: e.target.value }))} />
          </div>
        )}
        {/* Generate config button */}
        <button onClick={generateYealinkExpansion} style={{ marginBottom: 16 }}>Generate Yealink Expansion Config</button>
        {/* Output area for generated config */}
        <div className="output" style={{ marginBottom: 16 }}>
          <textarea value={yealinkOutput} readOnly rows={6} style={{ width: '100%', marginTop: 8 }} />
        </div>
        {/* Graphical preview of Yealink expansion module keys */}
        <div style={{ background: '#f8fbff', border: '1px solid #b5d6f7', borderRadius: 8, padding: 12, marginBottom: 16 }}>
          <div style={{ marginBottom: 8 }}>
            <b>Preview:</b> Page
            {/* Page toggle buttons */}
            {[1,2,3].map(page => (
              <button
                key={page}
                type="button"
                style={{ margin: '0 4px', background: yealinkSection.sidecarPage === String(page) ? '#0078d4' : '#eee', color: yealinkSection.sidecarPage === String(page) ? '#fff' : '#333', border: 'none', borderRadius: 4, padding: '2px 8px', cursor: 'pointer' }}
                onClick={() => setYealinkSection(s => ({ ...s, sidecarPage: String(page) }))}
              >{page}</button>
            ))}
          </div>
          {/* 2x10 grid for each page */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 120px)', gap: 5 }}>
            {Array.from({ length: 20 }).map((_, idx) => {
              // Highlight the currently selected key
              const isCurrent = parseInt(yealinkSection.sidecarLine) === idx + 1 && yealinkSection.sidecarPage === String(Math.ceil((idx + 1) / 20) || '1');
              const label = isCurrent ? yealinkSection.label : '';
              const value = isCurrent ? yealinkSection.value : '';
              const type = isCurrent ? yealinkSection.templateType : '';
              const icon = EXP_TYPE_ICONS[type || 'default'];
              const tooltip = label ? `Line: ${yealinkSection.sidecarLine}\nType: ${type}\nLabel: ${label}\nValue: ${value}` : 'Empty';
              return (
                <div
                  key={idx}
                  style={{
                    padding: 5,
                    background: type === 'BLF' ? '#d6f5d6' : type === 'SpeedDial' ? '#d6e6f5' : '#e0f0ff',
                    border: '1px solid #aaa',
                    textAlign: 'center',
                    borderRadius: 6,
                    fontSize: 12,
                    minHeight: 38,
                    position: 'relative',
                  }}
                  title={tooltip}
                >
                  <span style={{ fontSize: 18 }} title={EXP_TYPE_TOOLTIPS[type || 'default']}>{icon}</span>
                  <div>{label || <span style={{ color: '#bbb' }}>Empty</span>}</div>
                  <div style={{ fontSize: 10, color: '#888' }}>{value}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
      {/* Polycom Expansion Module Preview and Form */}
      <div style={{ flex: 1, minWidth: 320 }}>
        <h3>Polycom VVX Color Expansion Module</h3>
        {/* Device image for user reference */}
        <img src="/expansion/polycomVVX_Color_Exp_Module_2201.jpeg" alt="Polycom VVX Color Expansion Module" style={{ width: '100%', maxWidth: 260, marginBottom: 8, borderRadius: 8, border: '1px solid #ccc' }} />
        {/* Instructions for users */}
        <div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 12, margin: '16px 0' }}>
          <b>Instructions:</b> Fill out the form below to generate a config for a Polycom expansion key. The preview grid below shows the button layout for each page (1–3). Hover over any key for details. <br />
          <b>Linekey Index:</b> The key position to configure (1–84). Keys 1–28 appear on Page 1, 29–56 on Page 2, and 57–84 on Page 3. Use the buttons on the bottom of the module to switch pages during use.
        </div>
        {/* Polycom config form */}
        <div className="form-group" style={{ marginBottom: 16 }}>
          <label>Linekey Index (1-84):
            <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title="The key position to configure (1–84). Keys 1–28 appear on Page 1, 29–56 on Page 2, and 57–84 on Page 3. Use the buttons on the bottom of the module to switch pages during use.">ℹ️</span>
          </label>
          <input type="number" min="1" max="84" value={polycomSection.linekeyIndex} onChange={e => setPolycomSection(s => ({ ...s, linekeyIndex: e.target.value }))} />
        </div>
        <div className="form-group" style={{ marginBottom: 16 }}>
          <label>Address (e.g. 1001@ip):
            <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title="The SIP address or extension for this key.">ℹ️</span>
          </label>
          <input type="text" value={polycomSection.address} onChange={e => setPolycomSection(s => ({ ...s, address: e.target.value }))} />
        </div>
        <div className="form-group" style={{ marginBottom: 16 }}>
          <label>Label:
            <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title="The text label that will appear on the phone's display for this key.">ℹ️</span>
          </label>
          <input type="text" value={polycomSection.label} onChange={e => setPolycomSection(s => ({ ...s, label: e.target.value }))} />
        </div>
        <div className="form-group" style={{ marginBottom: 16 }}>
          <label>Type:
            <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title="The function type for this key (e.g., automata for BLF, normal for speed dial).">ℹ️</span>
          </label>
          <input type="text" value={polycomSection.type} onChange={e => setPolycomSection(s => ({ ...s, type: e.target.value }))} />
        </div>
        <div className="form-group" style={{ marginBottom: 16 }}>
          <label>Linekey Category:
            <span style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }} title="The key category (BLF, EFK, etc.).">ℹ️</span>
          </label>
          <input type="text" value={polycomSection.linekeyCategory} onChange={e => setPolycomSection(s => ({ ...s, linekeyCategory: e.target.value }))} />
        </div>
        {/* Generate config button */}
        <button onClick={generatePolycomExpansion} style={{ marginBottom: 16 }}>Generate Polycom Expansion Config</button>
        {/* Output area for generated config */}
        <div className="output" style={{ marginBottom: 16 }}>
          <textarea value={polycomOutput} readOnly rows={6} style={{ width: '100%', marginTop: 8 }} />
        </div>
        {/* Graphical preview of Polycom expansion module keys */}
        <div style={{ background: '#f8fbff', border: '1px solid #b5d6f7', borderRadius: 8, padding: 12, marginBottom: 16 }}>
          <div style={{ marginBottom: 8 }}>
            <b>Preview:</b>
            {/* Page toggle buttons for Polycom preview */}
            {POLYCOM_PAGE_LABELS.map((label, i) => (
              <button
                key={label}
                type="button"
                style={{ margin: '0 4px', background: polycomSection.activePage === i ? '#0078d4' : '#eee', color: polycomSection.activePage === i ? '#fff' : '#333', border: 'none', borderRadius: 4, padding: '2px 8px', cursor: 'pointer' }}
                onClick={() => setPolycomSection(s => ({ ...s, activePage: i }))}
              >{label}</button>
            ))}
          </div>
          {/* 2x14 grid for each Polycom page (28 keys per page) */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 120px)', gap: 5 }}>
            {Array.from({ length: POLYCOM_KEYS_PER_PAGE }).map((_, idx) => {
              // Calculate global key index for Polycom expansion
              const globalIdx = polycomSection.activePage * POLYCOM_KEYS_PER_PAGE + idx + 1;
              // Highlight the currently selected key
              const isCurrent = parseInt(polycomSection.linekeyIndex) === globalIdx;
              const label = isCurrent ? polycomSection.label : '';
              const value = isCurrent ? polycomSection.address : '';
              const type = isCurrent ? polycomSection.type : '';
              const icon = EXP_TYPE_ICONS[type === 'automata' ? 'BLF' : type === 'normal' ? 'SpeedDial' : 'default'];
              const tooltip = label ? `Index: ${globalIdx}\nType: ${type}\nLabel: ${label}\nValue: ${value}` : 'Empty';
              return (
                <div
                  key={idx}
                  style={{
                    padding: 5,
                    background: type === 'automata' ? '#d6f5d6' : type === 'normal' ? '#d6e6f5' : '#e0f0ff',
                    border: '1px solid #aaa',
                    textAlign: 'center',
                    borderRadius: 6,
                    fontSize: 12,
                    minHeight: 38,
                    position: 'relative',
                  }}
                  title={tooltip}
                >
                  <span style={{ fontSize: 18 }} title={EXP_TYPE_TOOLTIPS[type === 'automata' ? 'BLF' : type === 'normal' ? 'SpeedDial' : 'default']}>{icon}</span>
                  <div>{label || <span style={{ color: '#bbb' }}>Empty</span>}</div>
                  <div style={{ fontSize: 10, color: '#888' }}>{value}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ExpansionModuleTab;
