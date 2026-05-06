#!/usr/bin/env python3
"""Create a Windows desktop shortcut that launches the Scrape Manager GUI.

Run once:
    python create_shortcut.py

What it does:
  1. Creates "Scrape Manager.lnk" on your Desktop pointing to pythonw.exe
  2. Sets the shortcut icon to assets/123net.ico
  3. Registers the AppUserModelID in HKCU so pinned taskbar buttons show
     the 123net logo (not the Python default icon)
  4. Sets the AppUserModelID property on the shortcut itself so Windows
     groups the pinned shortcut with the running app as a single button

After running:
  - Unpin any old "Scrape Manager" entry from your taskbar first
  - Right-click "Scrape Manager" on the Desktop → Pin to taskbar
"""

import subprocess
import sys
import winreg
from pathlib import Path

APP_AUMID = "123net.ScrapeManager.1"

# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent
SCRIPT       = PROJECT_ROOT / "scrape_gui.py"

_desktop_raw = subprocess.check_output(
    ["powershell.exe", "-NoProfile", "-Command",
     "[Environment]::GetFolderPath('Desktop')"],
    text=True,
).strip()
DESKTOP  = Path(_desktop_raw)
SHORTCUT = DESKTOP / "Scrape Manager.lnk"

_python = Path(sys.executable)
PYTHONW = _python.parent / "pythonw.exe"
if not PYTHONW.exists():
    PYTHONW = _python

_ico = PROJECT_ROOT / "assets" / "123net.ico"
ICO_PATH = str(_ico) if _ico.exists() else f"{PYTHONW},0"

# ── Step 1: create the .lnk via PowerShell WScript.Shell ─────────────────────

print("Creating shortcut on Desktop…")

ps_script = f"""
$ws  = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut('{SHORTCUT}')
$lnk.TargetPath       = '{PYTHONW}'
$lnk.Arguments        = '"{SCRIPT}"'
$lnk.WorkingDirectory = '{PROJECT_ROOT}'
$lnk.IconLocation     = '{ICO_PATH}'
$lnk.Description      = 'FreePBX Scrape Manager'
$lnk.Save()
"""

result = subprocess.run(
    ["powershell.exe", "-NoProfile", "-Command", ps_script],
    capture_output=True, text=True,
)
if result.returncode != 0:
    print("ERROR: could not create shortcut:")
    print(result.stderr)
    sys.exit(1)

print(f"  {SHORTCUT}")

# ── Step 2: register the AUMID icon in the registry ──────────────────────────
# HKCU\Software\Classes\AppUserModelId\<AUMID>
#   IconUri     = path to .ico   → taskbar uses this for pinned buttons
#   DisplayName = human label

print(f"Registering AUMID '{APP_AUMID}' in registry…")

reg_key = rf"Software\Classes\AppUserModelId\{APP_AUMID}"
try:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_key) as key:
        winreg.SetValueEx(key, "IconUri",     0, winreg.REG_SZ, ICO_PATH)
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "Scrape Manager")
    print(f"  HKCU\\{reg_key}")
except Exception as exc:
    print(f"  WARNING: registry write failed ({exc}) — icon may not persist when pinned")

# ── Step 3: stamp the AUMID onto the shortcut's IPropertyStore ───────────────
# Windows uses the shortcut's AUMID to match a pinned button to the running app.
# Without this, pinning the shortcut creates a second button alongside the app.

print("Stamping AUMID onto shortcut property store…")

# PKEY_AppUserModel_ID = {9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}, 5
# We do this via a small C# snippet compiled inline by PowerShell.
ps_aumid = f"""
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

[ComImport, Guid("000214F9-0000-0000-C000-000000000046"),
 InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IShellLinkW {{
    void GetPath([MarshalAs(UnmanagedType.LPWStr)] System.Text.StringBuilder pszFile, int cch, IntPtr pfd, uint fFlags);
    void GetIDList(out IntPtr ppidl);
    void SetIDList(IntPtr pidl);
    void GetDescription([MarshalAs(UnmanagedType.LPWStr)] System.Text.StringBuilder pszName, int cch);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string pszName);
    void GetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] System.Text.StringBuilder pszDir, int cch);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string pszDir);
    void GetArguments([MarshalAs(UnmanagedType.LPWStr)] System.Text.StringBuilder pszArgs, int cch);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string pszArgs);
    void GetHotkey(out ushort pwHotkey);
    void SetHotkey(ushort wHotkey);
    void GetShowCmd(out int piShowCmd);
    void SetShowCmd(int iShowCmd);
    void GetIconLocation([MarshalAs(UnmanagedType.LPWStr)] System.Text.StringBuilder pszIconPath, int cch, out int piIcon);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string pszIconPath, int iIcon);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string pszPathRel, uint dwReserved);
    void Resolve(IntPtr hwnd, uint fFlags);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string pszFile);
}}

[ComImport, Guid("0000010B-0000-0000-C000-000000000046"),
 InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IPersistFile {{
    void GetClassID(out Guid pClassID);
    [PreserveSig] int IsDirty();
    void Load([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, uint dwMode);
    void Save([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, [MarshalAs(UnmanagedType.Bool)] bool fRemember);
    void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string pszFileName);
    void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string ppszFileName);
}}

[StructLayout(LayoutKind.Sequential, Pack=4)]
struct PROPERTYKEY {{
    public Guid fmtid;
    public uint pid;
}}

[ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"),
 InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IPropertyStore {{
    void GetCount(out uint cProps);
    void GetAt(uint iProp, out PROPERTYKEY pkey);
    void GetValue(ref PROPERTYKEY key, out PropVariant pv);
    void SetValue(ref PROPERTYKEY key, ref PropVariant pv);
    void Commit();
}}

[StructLayout(LayoutKind.Explicit)]
struct PropVariant {{
    [FieldOffset(0)] public ushort vt;
    [FieldOffset(8)] public IntPtr pszVal;
}}

public static class AumidHelper {{
    static readonly Guid CLSID_ShellLink = new Guid("00021401-0000-0000-C000-000000000046");
    static readonly PROPERTYKEY PKEY_AppUserModel_ID = new PROPERTYKEY {{
        fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"),
        pid   = 5
    }};

    [DllImport("ole32.dll")]
    static extern int CoCreateInstance(ref Guid rclsid, IntPtr pUnkOuter, uint dwClsContext, ref Guid riid, out IntPtr ppv);

    [DllImport("ole32.dll")]
    static extern void PropVariantClear(ref PropVariant pv);

    [DllImport("propsys.dll", CharSet=CharSet.Unicode)]
    static extern int InitPropVariantFromString(string psz, out PropVariant ppropvar);

    public static void SetAumid(string lnkPath, string aumid) {{
        var CLSID = CLSID_ShellLink;
        var IID_IShellLinkW    = new Guid("000214F9-0000-0000-C000-000000000046");
        var IID_IPersistFile   = new Guid("0000010B-0000-0000-C000-000000000046");
        var IID_IPropertyStore = new Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99");

        IntPtr psl;
        int hr = CoCreateInstance(ref CLSID, IntPtr.Zero, 1, ref IID_IShellLinkW, out psl);
        if (hr != 0) throw new COMException("CoCreateInstance IShellLinkW", hr);

        var sl  = (IShellLinkW)  Marshal.GetObjectForIUnknown(psl);
        var pf  = (IPersistFile) sl;
        var ps  = (IPropertyStore) sl;

        pf.Load(lnkPath, 0);

        PropVariant pv;
        InitPropVariantFromString(aumid, out pv);
        var key = PKEY_AppUserModel_ID;
        ps.SetValue(ref key, ref pv);
        PropVariantClear(ref pv);
        ps.Commit();

        pf.Save(lnkPath, true);
    }}
}}
"@ -Language CSharp

[AumidHelper]::SetAumid('{SHORTCUT}', '{APP_AUMID}')
"""

result2 = subprocess.run(
    ["powershell.exe", "-NoProfile", "-Command", ps_aumid],
    capture_output=True, text=True,
)
if result2.returncode == 0:
    print("  AUMID stamped onto shortcut.")
else:
    print(f"  NOTE: could not stamp AUMID onto shortcut ({result2.stderr.strip()[:120]})")
    print("  The icon will still appear correctly on the Desktop shortcut.")

# ── Done ─────────────────────────────────────────────────────────────────────

print()
print("Done.  Next steps:")
print("  1. If 'Scrape Manager' is already pinned to the taskbar, unpin it:")
print("     Right-click the taskbar button → Unpin from taskbar")
print("  2. Right-click 'Scrape Manager' on your Desktop → Pin to taskbar")
print("  3. The 123net logo will now show on the pinned button.")
