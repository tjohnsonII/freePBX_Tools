import re

tsx_path = 'e:/DevTools/freepbx-tools/PolycomYealinkMikrotikSwitchConfig-main/PolycomYealinkMikrotikSwitchConfig-main/src/App.tsx'
css_path = 'e:/DevTools/freepbx-tools/PolycomYealinkMikrotikSwitchConfig-main/PolycomYealinkMikrotikSwitchConfig-main/src/App.css'

content = open(tsx_path, 'r', encoding='utf-8').read()

# ──────────────────────────────────────────────────────────────
# 1. TABS BAR – line 758
# <div className="tabs" style={{ display: 'flex', gap: 0, marginBottom: 16 }}>
# → remove the style, CSS will handle it
content = content.replace(
    '<div className="tabs" style={{ display: \'flex\', gap: 0, marginBottom: 16 }}>',
    '<div className="tabs">'
)

# 2. TAB BUTTONS (lines 764-779) – remove the entire style block
# We can fully replace with CSS + .active class which is already set via className
old_tab_btn_style = '''            style={{
              border: 'none',
              borderBottom: activeTab === tab.key ? '3px solid var(--brand-blue)' : '2px solid var(--app-border)',
              background: activeTab === tab.key ? 'var(--app-surface-2)' : 'var(--app-surface)',
              color: activeTab === tab.key ? 'var(--brand-blue)' : 'var(--app-fg)',
              fontWeight: activeTab === tab.key ? 600 : 400,
              padding: '10px 24px',
              borderTopLeftRadius: idx === 0 ? 8 : 0,
              borderTopRightRadius: idx === TABS.length - 1 ? 8 : 0,
              marginRight: 2,
              outline: 'none',
              cursor: 'pointer',
              transition: 'background 0.2s, color 0.2s, border-bottom 0.2s',
              boxShadow: activeTab === tab.key ? '0 2px 8px rgba(0,0,0,0.04)' : 'none',
              minWidth: 120,
            }}'''
content = content.replace(old_tab_btn_style, '')

# 3. REFERENCE TAB CONTAINER (lines 788-795)
old_ref = '''        <div
          style={{
            margin: '24px 0',
            maxWidth: 900,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center', // Center the content horizontally
          }}
        >'''
new_ref = '        <div className="ref-container">'
content = content.replace(old_ref, new_ref)

# 4. REFERENCE h2 (line 797)
content = content.replace(
    "<h2 style={{ alignSelf: 'flex-start', textAlign: 'left', width: '100%' }}>Reference</h2>",
    '<h2 className="ref-h2">Reference</h2>'
)

# 5. REFERENCE SUBNAV CONTAINER (lines 799-806)
old_subnav = '''          <div
            style={{
              display: 'flex',
              gap: 8,
              marginBottom: 24,
              alignSelf: 'center', // Center the subnav
            }}
          >'''
new_subnav = '          <div className="ref-subnav">'
content = content.replace(old_subnav, new_subnav)

# 6. REFERENCE SUBNAV BUTTONS (lines 808-822) – remove style block
old_subnav_btn = '''                style={{
                  border: 'none',
                  borderBottom: referenceSubtab === sub.key ? '3px solid #0078d4' : '2px solid #ccc',
                  background: referenceSubtab === sub.key ? '#f7fbff' : '#f4f4f4',
                  color: referenceSubtab === sub.key ? '#0078d4' : '#333',
                  fontWeight: referenceSubtab === sub.key ? 600 : 400,
                  padding: '8px 20px',
                  borderRadius: 6,
                  cursor: 'pointer',
                  minWidth: 100,
                }}'''
content = content.replace(old_subnav_btn, '')

# 7. REFERENCE SUBTAB CONTENT (line 829)
content = content.replace(
    "<div style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>",
    '<div className="ref-content">'
)

# 8-9. REFERENCE PHONES SUBTAB inner + h2 (lines 831-832)
content = content.replace(
    "<div style={{ width: '100%', textAlign: 'left' }}>\n                <h2 style={{ textAlign: 'left' }}>Phone Config Reference (Legend)</h2>",
    '<div className="ref-section">\n                <h2>Phone Config Reference (Legend)</h2>'
)

# 10. TABLES FLEX CONTAINER (line 833)
content = content.replace(
    "<div style={{ marginTop: 16, display: 'flex', gap: 40, flexWrap: 'wrap', justifyContent: 'center' }}>",
    '<div className="ref-tables-flex">'
)

# 11. POLYCOM BRAND COL (line 835)
content = content.replace(
    "<div style={{ flex: 1, minWidth: 350, textAlign: 'left' }}>\n                    <h3 style={{ textAlign: 'left' }}>Polycom</h3>",
    '<div className="ref-brand-col">\n                    <h3>Polycom</h3>'
)

# 12. REFERENCE TABLE – remove inline style (class already set)
content = content.replace(
    'className="reference-table" style={{ width: \'100%\', borderCollapse: \'collapse\', marginBottom: 16 }}',
    'className="reference-table"'
)

# 13. TABLE HEADER ROWS (lines 839, 869)
content = content.replace(
    "<tr style={{ background: '#f4f4f4' }}>",
    '<tr>'
)

# 14. TABLE HEADER CELLS
content = content.replace(
    "<th style={{ textAlign: 'left', padding: '6px 12px', borderBottom: '2px solid #ccc' }}>Setting</th>",
    '<th>Setting</th>'
)
content = content.replace(
    "<th style={{ textAlign: 'left', padding: '6px 12px', borderBottom: '2px solid #ccc' }}>Description</th>",
    '<th>Description</th>'
)

# 15. POLYCOM h4 and ul (lines 856-857)
content = content.replace(
    "<h4 style={{ marginTop: 12, textAlign: 'left' }}>Common Polycom Features</h4>\n                    <ul style={{ marginLeft: 20, textAlign: 'left' }}>",
    '<h4 className="ref-h4">Common Polycom Features</h4>\n                    <ul className="ref-ul">'
)

# 16. YEALINK BRAND COL (line 865)
content = content.replace(
    "<div style={{ flex: 1, minWidth: 350, textAlign: 'left' }}>\n                  {/* Yealink Reference Table */}\n                  <div style={{ flex: 1, minWidth: 350, textAlign: 'left' }}>\n                    <h3 style={{ textAlign: 'left' }}>Yealink</h3>",
    '<div className="ref-brand-col">\n                  {/* Yealink Reference Table */}\n                  <div className="ref-brand-col">\n                    <h3>Yealink</h3>'
)
# Direct yealink col
content = content.replace(
    "                  {/* Yealink Reference Table */}\n                  <div style={{ flex: 1, minWidth: 350, textAlign: 'left' }}>\n                    <h3 style={{ textAlign: 'left' }}>Yealink</h3>",
    "                  {/* Yealink Reference Table */}\n                  <div className=\"ref-brand-col\">\n                    <h3>Yealink</h3>"
)

# 17. YEALINK h4 and ul (lines 886-887)
content = content.replace(
    "<h4 style={{ marginTop: 12, textAlign: 'left' }}>Common Yealink Features</h4>\n                    <ul style={{ marginLeft: 20, textAlign: 'left' }}>",
    '<h4 className="ref-h4">Common Yealink Features</h4>\n                    <ul className="ref-ul">'
)

# 18. MIKROTIK SUBTAB
content = content.replace(
    "{referenceSubtab === 'mikrotik' && (\n              <div style={{ width: '100%', textAlign: 'left' }}>",
    "{referenceSubtab === 'mikrotik' && (\n              <div className=\"ref-section\">"
)
content = content.replace(
    "<div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 16, marginBottom: 32 }}>\n                  <h4 style={{ marginTop: 0 }}>What does each Mikrotik config template do?</h4>\n                  <ul style={{ marginLeft: 20 }}>",
    '<div className="ref-card">\n                  <h4>What does each Mikrotik config template do?</h4>\n                  <ul>'
)

# 19. SWITCHES SUBTAB
content = content.replace(
    "{referenceSubtab === 'switches' && (\n              <div style={{ width: '100%', textAlign: 'left' }}>",
    "{referenceSubtab === 'switches' && (\n              <div className=\"ref-section\">"
)
content = content.replace(
    "<div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 16, marginBottom: 32 }}>\n                  <h4 style={{ marginTop: 0 }}>What does each Switch config template do?</h4>\n                  <ul style={{ marginLeft: 20 }}>",
    '<div className="ref-card">\n                  <h4>What does each Switch config template do?</h4>\n                  <ul>'
)

# 20. PBX SUBTAB
content = content.replace(
    "{referenceSubtab === 'pbx' && (\n              <div style={{ width: '100%', textAlign: 'left' }}>",
    "{referenceSubtab === 'pbx' && (\n              <div className=\"ref-section\">"
)
content = content.replace(
    "<div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 16, marginBottom: 32 }}>\n                  <h4 style={{ marginTop: 0 }}>PBX Import/Export and Config Types</h4>\n                  <ul style={{ marginLeft: 20 }}>",
    '<div className="ref-card">\n                  <h4>PBX Import/Export and Config Types</h4>\n                  <ul>'
)

# 21. PHONE TAB h2 (line 1071)
content = content.replace(
    "<h2 style={{marginTop:0}}>Phone Config Generator</h2>",
    '<h2 className="section-h2">Phone Config Generator</h2>'
)

# 22. INFO BOX (line 1072)
content = content.replace(
    "<div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 16, marginBottom: 24, maxWidth: 700, marginLeft: 'auto', marginRight: 'auto', textAlign: 'left' }}>\n            <h3 style={{ marginTop: 0 }}>What does each config generator do?</h3>\n            <ul style={{ marginLeft: 20 }}>",
    '<div className="info-box">\n            <h3>What does each config generator do?</h3>\n            <ul>'
)

# 23. SCRAPER PANEL (line 1082)
content = content.replace(
    "          {/* Load from Scraper Panel */}\n          <div style={{ background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 16, marginBottom: 20, maxWidth: 700, marginLeft: 'auto', marginRight: 'auto' }}>",
    "          {/* Load from Scraper Panel */}\n          <div className=\"scraper-panel\">"
)

# 24. SCRAPER HEADER ROW (line 1083)
content = content.replace(
    "<div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 8 }}>",
    '<div className="scraper-header">'
)

# 25. SCRAPER STRONG (line 1084)
content = content.replace(
    "<strong style={{ fontSize: 14 }}>Load from Webscraper</strong>",
    '<strong className="scraper-strong">Load from Webscraper</strong>'
)

# 26. SCRAPER STATUS SPAN (line 1085) – dynamic, use conditional class
content = content.replace(
    "<span style={{ fontSize: 12, color: scraperOnlinePhone ? '#16794a' : scraperOnlinePhone === false ? '#b42318' : '#888' }}>",
    "<span className={scraperOnlinePhone === null ? 'scraper-status-pending' : scraperOnlinePhone ? 'scraper-status-online' : 'scraper-status-offline'}>"
)

# 27. SCRAPER SELECT ROW (line 1089)
content = content.replace(
    "<div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>",
    '<div className="scraper-select-row">'
)

# 28. SCRAPER LABELS (lines 1090, 1106)
content = content.replace(
    '<label htmlFor="phone-scraper-handle" style={{ fontSize: 13, fontWeight: 600 }}>Handle:</label>',
    '<label htmlFor="phone-scraper-handle" className="scraper-label">Handle:</label>'
)
content = content.replace(
    '<label htmlFor="phone-scraper-device" style={{ fontSize: 13, fontWeight: 600 }}>Device:</label>',
    '<label htmlFor="phone-scraper-device" className="scraper-label">Device:</label>'
)

# 29. SCRAPER HANDLE SELECT (line 1096)
content = content.replace(
    "style={{ minWidth: 200, padding: '4px 8px' }}\n                title=\"Select a company handle to load scraped devices\"",
    "className=\"scraper-handle-select\"\n                title=\"Select a company handle to load scraped devices\""
)

# 30. SCRAPER DEVICE SELECT (line 1111)
content = content.replace(
    "style={{ minWidth: 220, padding: '4px 8px' }}\n                    title=\"Select a device to pre-fill config fields\"",
    "className=\"scraper-device-select\"\n                    title=\"Select a device to pre-fill config fields\""
)

# 31. SCRAPER SHOW AREA (line 1125)
content = content.replace(
    '<div style={{ marginTop: 10 }}>',
    '<div className="scraper-show-area">'
)

# 32. SCRAPER TOGGLE BUTTON (line 1129)
content = content.replace(
    "style={{ fontSize: 12, padding: '2px 10px', marginBottom: 6 }}\n                >",
    'className="scraper-toggle-btn"\n                >'
)

# 33. SCRAPER PRE (line 1134)
content = content.replace(
    "<pre style={{ background: '#0d1117', color: '#3fb950', fontSize: 11, padding: 10, borderRadius: 6, maxHeight: 240, overflowY: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: 0 }}>",
    '<pre className="scraper-pre">'
)

# 34. SCRAPER OFFLINE MESSAGE (line 1141)
content = content.replace(
    "<p style={{ margin: '6px 0 0', fontSize: 12, color: '#b42318' }}>",
    '<p className="scraper-offline">'
)

# 35. FORM SECTION style (line 1147) – class already present, remove inline
content = content.replace(
    '<div className="form-section" style={{marginBottom:24}}>',
    '<div className="form-section">'
)

# 36. FaInfoCircle spans – marginLeft 4, cursor pointer, color #0078d4
# These appear many times with slightly different surrounding context.
# Replace all occurrences of the common pattern
content = content.replace(
    "style={{ marginLeft: 4, cursor: 'pointer', color: '#0078d4' }}",
    'className="info-icon"'
)

# 37. Remaining "style={{ marginLeft: 4, color: '#0078d4', cursor: 'pointer' }}" variant
content = content.replace(
    "style={{ marginLeft: 4, color: '#0078d4', cursor: 'pointer' }}",
    'className="info-icon"'
)

# 38. label marginLeft: 16 (many forms)
content = content.replace(
    'style={{marginLeft:16}}',
    'className="label-ml"'
)
content = content.replace(
    'style={{ marginLeft: 16 }}',
    'className="label-ml"'
)

# 39. marginTop: 8 buttons
content = content.replace(
    "onClick={generateConfig} style={{marginTop:8}}",
    "onClick={generateConfig} className=\"btn-mt\""
)
content = content.replace(
    "style={{marginTop:8}}",
    'className="btn-mt"'
)
# style={{ marginTop: 8 }} for buttons
content = content.replace(
    'onClick={generateYealinkExpansion} style={{ marginTop: 8, marginRight: 8 }}',
    'onClick={generateYealinkExpansion} className="btn-mt btn-mr"'
)
content = content.replace(
    'onClick={generateYealinkExpansionAll} style={{ marginTop: 8 }}',
    'onClick={generateYealinkExpansionAll} className="btn-mt"'
)
content = content.replace(
    'onClick={generatePolycomExpansion} style={{ marginTop: 8, marginRight: 8 }}',
    'onClick={generatePolycomExpansion} className="btn-mt btn-mr"'
)
content = content.replace(
    'onClick={generatePolycomExpansionAll} style={{ marginTop: 8 }}',
    'onClick={generatePolycomExpansionAll} className="btn-mt"'
)
content = content.replace(
    "onClick={generatePolycomMWI} style={{ marginTop: 8 }}",
    'onClick={generatePolycomMWI} className="btn-mt"'
)

# 40. Output divs with marginTop: 16
content = content.replace(
    'className="output" style={{ marginTop: 16 }}',
    'className="output"'
)
content = content.replace(
    'className="output" style={{ marginTop: 12 }}',
    'className="output"'
)

# 41. Textarea width 100% marginTop
content = content.replace(
    "style={{ width: '100%', marginTop: 16 }}",
    'className="full-width-ta"'
)
content = content.replace(
    "style={{ width: '100%' }}",
    'className="full-width-ta"'
)

# 42. Expansion tab container (line 1404)
content = content.replace(
    "<div style={{ maxWidth: 1100, margin: '0 auto', textAlign: 'center' }}>",
    '<div className="expansion-container">'
)
content = content.replace(
    "<h2 style={{ marginBottom: 24 }}>Expansion Module Code Generators</h2>",
    '<h2 className="expansion-h2">Expansion Module Code Generators</h2>'
)
content = content.replace(
    "<div style={{ display: 'flex', gap: 40, justifyContent: 'center', alignItems: 'flex-start', flexWrap: 'wrap' }}>",
    '<div className="expansion-flex">'
)

# Yealink expansion section div
content = content.replace(
    "<div style={{ flex: 1, minWidth: 350 }}>\n              <img src=\"/expansion/yealinkexp40.jpeg\"",
    '<div className="expansion-col">\n              <img src="/expansion/yealinkexp40.jpeg"'
)

# Expansion image styles
content = content.replace(
    "style={{ maxWidth: 220, marginBottom: 8, borderRadius: 8 }}",
    'className="expansion-img"'
)

# Expansion instructions box
content = content.replace(
    "<div style={{ background: '#eef6fb', border: '1px solid #cce1fa', borderRadius: 8, padding: 10, marginBottom: 12, fontSize: 14 }}>",
    '<div className="expansion-instructions">'
)

# Polycom expansion section div
content = content.replace(
    "<div style={{ flex: 1, minWidth: 350 }}>\n              <img src=\"/expansion/polycomVVX_Color_Exp_Module_2201.jpeg\"",
    '<div className="expansion-col">\n              <img src="/expansion/polycomVVX_Color_Exp_Module_2201.jpeg"'
)

# Expansion form group max-width
content = content.replace(
    "<div className=\"form-group\" style={{ textAlign: 'left', margin: '0 auto', maxWidth: 320 }}>",
    '<div className="form-group expansion-form-group">'
)

# Sidecar refresh input width
content = content.replace(
    'title="Sidecar page (1-3)" onChange={e => setYealinkSection(s => ({ ...s, sidecarPage: e.target.value }))} style={{ width: 60 }}',
    'title="Sidecar page (1-3)" onChange={e => setYealinkSection(s => ({ ...s, sidecarPage: e.target.value }))} className="narrow-input"'
)
content = content.replace(
    'title="Button position (1-20)" onChange={e => setYealinkSection(s => ({ ...s, sidecarLine: e.target.value }))} style={{ width: 60 }}',
    'title="Button position (1-20)" onChange={e => setYealinkSection(s => ({ ...s, sidecarLine: e.target.value }))} className="narrow-input"'
)

# Expansion yealink buttons
content = content.replace(
    'onClick={generateYealinkExpansion} style={{ marginTop: 8, marginRight: 8 }}',
    'onClick={generateYealinkExpansion} className="btn-mt btn-mr"'
)
content = content.replace(
    'onClick={generateYealinkExpansionAll} style={{ marginTop: 8 }}',
    'onClick={generateYealinkExpansionAll} className="btn-mt"'
)

# Expansion output marginTop 12
content = content.replace(
    'className="output" style={{ marginTop: 12 }}',
    'className="output"'
)

# Yealink preview grid
content = content.replace(
    "<div style={{ marginTop: 16, background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 12 }}>\n                <b>Preview: Page {yealinkSection.sidecarPage}</b>",
    '<div className="expansion-preview">\n                <b>Preview: Page {yealinkSection.sidecarPage}</b>'
)
content = content.replace(
    "<div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 40px)', gap: 8, justifyContent: 'center', marginTop: 8 }}>",
    '<div className="expansion-grid expansion-grid-2col">'
)

# Polycom preview grid
content = content.replace(
    "<div style={{ marginTop: 16, background: '#f7fbff', border: '1px solid #cce1fa', borderRadius: 8, padding: 12 }}>\n                <b>Preview: 28 keys (4 columns × 7 rows)</b>",
    '<div className="expansion-preview">\n                <b>Preview: 28 keys (4 columns \u00d7 7 rows)</b>'
)
content = content.replace(
    "<div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 40px)', gap: 8, justifyContent: 'center', marginTop: 8 }}>",
    '<div className="expansion-grid expansion-grid-4col">'
)

# Full config tab textarea
content = content.replace(
    "<textarea title=\"Generated full config output\" value={output} readOnly rows={10} className=\"full-width-ta\" />",
    '<textarea title="Generated full config output" value={output} readOnly rows={10} className="full-width-ta" />'
)

# FBPX textarea
content = content.replace(
    "a ref={fpbxDownloadRef} style={{ display: 'none' }}",
    'a ref={fpbxDownloadRef} className="hidden-link"'
)

# Linekey generate button
content = content.replace(
    'style={{ marginLeft: 16 }}>Generate Linekey Config</button>',
    'className="btn-ml">Generate Linekey Config</button>'
)
content = content.replace(
    'style={{ marginLeft: 16 }}>Generate External Speed Dial</button>',
    'className="btn-ml">Generate External Speed Dial</button>'
)

open(tsx_path, 'w', encoding='utf-8').write(content)
print('TSX done')

# ──────────────────────────────────────────────────────────────
# CSS ADDITIONS
css_additions = '''
/* ─── Tabs bar ──────────────────────────────── */
.tabs {
  display: flex;
  gap: 0;
  margin-bottom: 16px;
}

.tabs button {
  border: none;
  border-bottom: 2px solid var(--app-border);
  background: var(--app-surface);
  color: var(--app-fg);
  font-weight: 400;
  padding: 10px 24px;
  margin-right: 2px;
  outline: none;
  cursor: pointer;
  transition: background 0.2s, color 0.2s, border-bottom 0.2s;
  box-shadow: none;
  min-width: 120px;
}

.tabs button:first-child { border-top-left-radius: 8px; }
.tabs button:last-child  { border-top-right-radius: 8px; }

.tabs button.active {
  border-bottom: 3px solid var(--brand-blue);
  background: var(--app-surface-2);
  color: var(--brand-blue);
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}

/* ─── Reference tab ─────────────────────────── */
.ref-container {
  margin: 24px 0;
  max-width: 900px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.ref-h2 {
  align-self: flex-start;
  text-align: left;
  width: 100%;
}

.ref-subnav {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
  align-self: center;
}

.ref-subnav button {
  border: none;
  border-bottom: 2px solid #ccc;
  background: #f4f4f4;
  color: #333;
  font-weight: 400;
  padding: 8px 20px;
  border-radius: 6px;
  cursor: pointer;
  min-width: 100px;
}

.ref-subnav button.active {
  border-bottom: 3px solid #0078d4;
  background: #f7fbff;
  color: #0078d4;
  font-weight: 600;
}

.ref-content {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.ref-section { width: 100%; text-align: left; }

.ref-tables-flex {
  margin-top: 16px;
  display: flex;
  gap: 40px;
  flex-wrap: wrap;
  justify-content: center;
}

.ref-brand-col {
  flex: 1;
  min-width: 350px;
  text-align: left;
}

.ref-h4 { margin-top: 12px; text-align: left; }
.ref-ul  { margin-left: 20px; text-align: left; }

.reference-table {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 16px;
}

.reference-table thead tr { background: #f4f4f4; }
.reference-table th {
  text-align: left;
  padding: 6px 12px;
  border-bottom: 2px solid #ccc;
}

.ref-card {
  background: #f7fbff;
  border: 1px solid #cce1fa;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 32px;
}

.ref-card h4 { margin-top: 0; }
.ref-card > ul { margin-left: 20px; }

/* ─── Phone tab ─────────────────────────────── */
.section-h2 { margin-top: 0; }

.info-box {
  background: #f7fbff;
  border: 1px solid #cce1fa;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 24px;
  max-width: 700px;
  margin-left: auto;
  margin-right: auto;
  text-align: left;
}

.info-box h3 { margin-top: 0; }
.info-box > ul { margin-left: 20px; }

/* ─── Scraper panel ─────────────────────────── */
.scraper-panel {
  background: #f7fbff;
  border: 1px solid #cce1fa;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 20px;
  max-width: 700px;
  margin-left: auto;
  margin-right: auto;
}

.scraper-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.scraper-strong { font-size: 14px; }

.scraper-status-pending { font-size: 12px; color: #888; }
.scraper-status-online  { font-size: 12px; color: #16794a; }
.scraper-status-offline { font-size: 12px; color: #b42318; }

.scraper-select-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.scraper-label { font-size: 13px; font-weight: 600; }
.scraper-handle-select { min-width: 200px; padding: 4px 8px; }
.scraper-device-select { min-width: 220px; padding: 4px 8px; }
.scraper-show-area { margin-top: 10px; }

.scraper-toggle-btn {
  font-size: 12px;
  padding: 2px 10px;
  margin-bottom: 6px;
}

.scraper-pre {
  background: #0d1117;
  color: #3fb950;
  font-size: 11px;
  padding: 10px;
  border-radius: 6px;
  max-height: 240px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

.scraper-offline {
  margin: 6px 0 0;
  font-size: 12px;
  color: #b42318;
}

/* ─── Form helpers ──────────────────────────── */
.form-section { margin-bottom: 24px; }

.info-icon {
  margin-left: 4px;
  cursor: pointer;
  color: #0078d4;
}

.label-ml { margin-left: 16px; }
.btn-mt   { margin-top: 8px; }
.btn-mr   { margin-right: 8px; }
.btn-ml   { margin-left: 16px; }

.full-width-ta { width: 100%; }
.hidden-link   { display: none; }
.narrow-input  { width: 60px; }

/* ─── Expansion Module tab ──────────────────── */
.expansion-container {
  max-width: 1100px;
  margin: 0 auto;
  text-align: center;
}

.expansion-h2  { margin-bottom: 24px; }

.expansion-flex {
  display: flex;
  gap: 40px;
  justify-content: center;
  align-items: flex-start;
  flex-wrap: wrap;
}

.expansion-col {
  flex: 1;
  min-width: 350px;
}

.expansion-img {
  max-width: 220px;
  margin-bottom: 8px;
  border-radius: 8px;
}

.expansion-instructions {
  background: #eef6fb;
  border: 1px solid #cce1fa;
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 12px;
  font-size: 14px;
}

.expansion-form-group {
  text-align: left;
  margin: 0 auto;
  max-width: 320px;
}

.expansion-preview {
  margin-top: 16px;
  background: #f7fbff;
  border: 1px solid #cce1fa;
  border-radius: 8px;
  padding: 12px;
}

.expansion-grid {
  display: grid;
  gap: 8px;
  justify-content: center;
  margin-top: 8px;
}

.expansion-grid-2col { grid-template-columns: repeat(2, 40px); }
.expansion-grid-4col { grid-template-columns: repeat(4, 40px); }
'''

css_content = open(css_path, 'r', encoding='utf-8').read()
if '.tabs {' not in css_content:
    css_content += css_additions
    open(css_path, 'w', encoding='utf-8').write(css_content)
    print('CSS appended')
else:
    print('CSS already has .tabs, skipping append')