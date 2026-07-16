# Creates (or replaces) the Scrape Manager desktop shortcut with the correct
# Windows Python target, 123net icon, and AppUserModelID so the taskbar pin
# shows the same icon as the desktop shortcut.
#
# Usage: powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1

Add-Type @"
using System;
using System.Runtime.InteropServices;

[Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IPropertyStore {
    int GetCount(out uint count);
    int GetAt(uint index, out PROPERTYKEY key);
    int GetValue(ref PROPERTYKEY key, out PropVariant pv);
    int SetValue(ref PROPERTYKEY key, ref PropVariant pv);
    int Commit();
}

[StructLayout(LayoutKind.Sequential)]
public struct PROPERTYKEY {
    public Guid fmtid;
    public uint pid;
}

[StructLayout(LayoutKind.Explicit)]
public struct PropVariant {
    [FieldOffset(0)] public ushort vt;
    [FieldOffset(8)] public IntPtr ptr;
}

public class ShortcutProps {
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    public static extern int SHGetPropertyStoreFromParsingName(
        string path, IntPtr pbc, int flags, ref Guid riid, out IPropertyStore ppv);

    public static void SetAppUserModelId(string lnkPath, string appId) {
        var iid = new Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99");
        IPropertyStore store;
        int hr = SHGetPropertyStoreFromParsingName(lnkPath, IntPtr.Zero, 2, ref iid, out store);
        if (hr != 0) throw new Exception("SHGetPropertyStoreFromParsingName failed: 0x" + hr.ToString("X"));

        // PKEY_AppUserModel_ID = {9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}, pid 5
        var key = new PROPERTYKEY {
            fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"),
            pid = 5
        };
        var pv = new PropVariant { vt = 31 }; // VT_LPWSTR
        pv.ptr = Marshal.StringToCoTaskMemUni(appId);
        try {
            store.SetValue(ref key, ref pv);
            store.Commit();
        } finally {
            Marshal.FreeCoTaskMem(pv.ptr);
            Marshal.ReleaseComObject(store);
        }
    }
}
"@

$root       = Split-Path $PSScriptRoot -Parent
$iconPath   = Join-Path $root "assets\123net.ico"
$scriptPath = Join-Path $root "scrape_gui.py"
$appId      = "123net.ScrapeManager.1"

# Prefer project Python (no console window), fall back to py launcher
$winPython = "E:\DevTools\Python\pythonw.exe"
if (-not (Test-Path $winPython)) {
    $candidate = (Get-Command pythonw.exe -ErrorAction SilentlyContinue)?.Source
    if ($candidate) { $winPython = $candidate }
}
if (-not (Test-Path $winPython)) {
    Write-Error "Could not locate pythonw.exe. Install Python for Windows or set the path in this script."
    exit 1
}

$desktopPath  = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "Scrape Manager.lnk"

# Build the shortcut
$shell    = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath       = $winPython
$shortcut.Arguments        = "`"$scriptPath`""
$shortcut.WorkingDirectory = $root
$shortcut.Description      = "Scrape Manager - FreePBX Tools"
$shortcut.IconLocation     = "$iconPath,0"
$shortcut.WindowStyle      = 1
$shortcut.Save()

# Stamp the AppUserModelID so the pinned taskbar button groups with the running app
[ShortcutProps]::SetAppUserModelId($shortcutPath, $appId)

Write-Host "Shortcut created : $shortcutPath"
Write-Host "Target           : $winPython"
Write-Host "Icon             : $iconPath"
Write-Host "AppUserModelID   : $appId"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Unpin the old taskbar icon (right-click -> Unpin from taskbar)"
Write-Host "  2. Right-click the new desktop shortcut -> Pin to taskbar"
Write-Host "  The taskbar icon and the running app will both show 123net.ico"
