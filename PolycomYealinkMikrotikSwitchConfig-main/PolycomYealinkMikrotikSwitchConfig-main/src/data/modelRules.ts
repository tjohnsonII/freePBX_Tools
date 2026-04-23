// modelRules.ts — supported phone models and per-model config rules

export type Vendor = 'yealink' | 'polycom';
export type Target = 'phone' | 'sidecar' | 'combined';
export type BuildStyle = 'template' | 'adhoc';
export type SourceMode = 'scratch' | 'production';

export interface ModelRule {
  vendor: Vendor;
  label: string;
  dect: boolean;
  sidecarSupported: boolean;
  parkLineStart: number;
  sidecarStartIndex: number;
}

export const MODEL_RULES: Record<string, ModelRule> = {
  // ─── Yealink ─────────────────────────────────────────────────────────────
  'yealink|T19P':    { vendor: 'yealink', label: 'T19P',    dect: false, sidecarSupported: false, parkLineStart: 2,  sidecarStartIndex: 1  },
  'yealink|T21P':    { vendor: 'yealink', label: 'T21P',    dect: false, sidecarSupported: false, parkLineStart: 2,  sidecarStartIndex: 1  },
  'yealink|T23G':    { vendor: 'yealink', label: 'T23G',    dect: false, sidecarSupported: false, parkLineStart: 2,  sidecarStartIndex: 1  },
  'yealink|T27G':    { vendor: 'yealink', label: 'T27G',    dect: false, sidecarSupported: true,  parkLineStart: 4,  sidecarStartIndex: 1  },
  'yealink|T29G':    { vendor: 'yealink', label: 'T29G',    dect: false, sidecarSupported: true,  parkLineStart: 4,  sidecarStartIndex: 1  },
  'yealink|T33G':    { vendor: 'yealink', label: 'T33G',    dect: false, sidecarSupported: false, parkLineStart: 2,  sidecarStartIndex: 1  },
  'yealink|T40G':    { vendor: 'yealink', label: 'T40G',    dect: false, sidecarSupported: false, parkLineStart: 2,  sidecarStartIndex: 1  },
  'yealink|T41S':    { vendor: 'yealink', label: 'T41S',    dect: false, sidecarSupported: true,  parkLineStart: 4,  sidecarStartIndex: 1  },
  'yealink|T42S':    { vendor: 'yealink', label: 'T42S',    dect: false, sidecarSupported: true,  parkLineStart: 4,  sidecarStartIndex: 1  },
  'yealink|T43U':    { vendor: 'yealink', label: 'T43U',    dect: false, sidecarSupported: true,  parkLineStart: 4,  sidecarStartIndex: 1  },
  'yealink|T46S':    { vendor: 'yealink', label: 'T46S',    dect: false, sidecarSupported: true,  parkLineStart: 4,  sidecarStartIndex: 1  },
  'yealink|T46U':    { vendor: 'yealink', label: 'T46U',    dect: false, sidecarSupported: true,  parkLineStart: 4,  sidecarStartIndex: 1  },
  'yealink|T48S':    { vendor: 'yealink', label: 'T48S',    dect: false, sidecarSupported: true,  parkLineStart: 4,  sidecarStartIndex: 1  },
  'yealink|T48U':    { vendor: 'yealink', label: 'T48U',    dect: false, sidecarSupported: true,  parkLineStart: 4,  sidecarStartIndex: 1  },
  'yealink|T52S':    { vendor: 'yealink', label: 'T52S',    dect: false, sidecarSupported: true,  parkLineStart: 4,  sidecarStartIndex: 1  },
  'yealink|T53W':    { vendor: 'yealink', label: 'T53W',    dect: false, sidecarSupported: true,  parkLineStart: 4,  sidecarStartIndex: 1  },
  'yealink|T54W':    { vendor: 'yealink', label: 'T54W',    dect: false, sidecarSupported: true,  parkLineStart: 4,  sidecarStartIndex: 1  },
  'yealink|T57W':    { vendor: 'yealink', label: 'T57W',    dect: false, sidecarSupported: true,  parkLineStart: 4,  sidecarStartIndex: 1  },
  'yealink|T58W':    { vendor: 'yealink', label: 'T58W',    dect: false, sidecarSupported: true,  parkLineStart: 4,  sidecarStartIndex: 1  },
  'yealink|W60B':    { vendor: 'yealink', label: 'W60B',    dect: true,  sidecarSupported: false, parkLineStart: 2,  sidecarStartIndex: 1  },
  'yealink|W70B':    { vendor: 'yealink', label: 'W70B',    dect: true,  sidecarSupported: false, parkLineStart: 2,  sidecarStartIndex: 1  },
  'yealink|W80B':    { vendor: 'yealink', label: 'W80B',    dect: true,  sidecarSupported: false, parkLineStart: 2,  sidecarStartIndex: 1  },
  // ─── Polycom ─────────────────────────────────────────────────────────────
  'polycom|VVX300':  { vendor: 'polycom', label: 'VVX 300/310', dect: false, sidecarSupported: false, parkLineStart: 2, sidecarStartIndex: 1 },
  'polycom|VVX400':  { vendor: 'polycom', label: 'VVX 400/410', dect: false, sidecarSupported: true,  parkLineStart: 2, sidecarStartIndex: 1 },
  'polycom|VVX500':  { vendor: 'polycom', label: 'VVX 500',     dect: false, sidecarSupported: true,  parkLineStart: 2, sidecarStartIndex: 1 },
  'polycom|VVX600':  { vendor: 'polycom', label: 'VVX 600',     dect: false, sidecarSupported: true,  parkLineStart: 2, sidecarStartIndex: 1 },
  'polycom|VVX601':  { vendor: 'polycom', label: 'VVX 601',     dect: false, sidecarSupported: true,  parkLineStart: 2, sidecarStartIndex: 1 },
  'polycom|VVX450':  { vendor: 'polycom', label: 'VVX 450',     dect: false, sidecarSupported: true,  parkLineStart: 2, sidecarStartIndex: 1 },
  'polycom|VVX350':  { vendor: 'polycom', label: 'VVX 350',     dect: false, sidecarSupported: false, parkLineStart: 2, sidecarStartIndex: 1 },
  'polycom|VVX250':  { vendor: 'polycom', label: 'VVX 250',     dect: false, sidecarSupported: false, parkLineStart: 2, sidecarStartIndex: 1 },
  'polycom|VVX150':  { vendor: 'polycom', label: 'VVX 150',     dect: false, sidecarSupported: false, parkLineStart: 2, sidecarStartIndex: 1 },
  'polycom|TRIO8500':{ vendor: 'polycom', label: 'Trio 8500',   dect: false, sidecarSupported: false, parkLineStart: 1, sidecarStartIndex: 1 },
  'polycom|TRIO8800':{ vendor: 'polycom', label: 'Trio 8800',   dect: false, sidecarSupported: false, parkLineStart: 1, sidecarStartIndex: 1 },
};

export const YEALINK_MODELS = Object.entries(MODEL_RULES)
  .filter(([, r]) => r.vendor === 'yealink')
  .map(([key, r]) => ({ key, label: r.label }));

export const POLYCOM_MODELS = Object.entries(MODEL_RULES)
  .filter(([, r]) => r.vendor === 'polycom')
  .map(([key, r]) => ({ key, label: r.label }));
