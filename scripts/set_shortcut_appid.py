"""Stamp System.AppUserModel.ID on the Scrape Manager desktop shortcut.

Called by create_shortcut.bat after the VBScript creates the .lnk file.
Uses only stdlib ctypes — no extra packages needed.
"""

import ctypes
import os
import sys
import uuid
import winreg
from pathlib import Path

APP_ID   = "123net.ScrapeManager.1"
LNK_NAME = "Scrape Manager.lnk"


def _make_guid_bytes(guid_str: str) -> ctypes.Array:
    u = uuid.UUID(guid_str)
    arr = (ctypes.c_byte * 16)()
    ctypes.memmove(arr, u.bytes_le, 16)
    return arr


def set_appusermodel_id(lnk_path: str, app_id: str) -> None:
    GPS_READWRITE = 2
    VT_LPWSTR     = 31

    # PROPERTYKEY: GUID(16 bytes) + ULONG(4 bytes)
    class PROPERTYKEY(ctypes.Structure):
        _fields_ = [("fmtid", ctypes.c_byte * 16), ("pid", ctypes.c_ulong)]

    iid_bytes = _make_guid_bytes("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")

    fn = ctypes.windll.shell32.SHGetPropertyStoreFromParsingName
    fn.restype = ctypes.HRESULT
    fn.argtypes = [
        ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_int,
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
    ]

    ctypes.windll.ole32.CoInitialize(None)
    ppv = ctypes.c_void_p(0)
    hr  = fn(lnk_path, None, GPS_READWRITE, iid_bytes, ctypes.byref(ppv))
    if hr != 0:
        raise OSError(f"SHGetPropertyStoreFromParsingName: 0x{hr & 0xFFFFFFFF:08X}")

    # IPropertyStore vtable offsets:
    # 0=QueryInterface 1=AddRef 2=Release 3=GetCount 4=GetAt 5=GetValue 6=SetValue 7=Commit
    vtbl_ptr = ctypes.cast(ppv, ctypes.POINTER(ctypes.c_void_p)).contents.value
    vtbl     = ctypes.cast(vtbl_ptr, ctypes.POINTER(ctypes.c_void_p))

    F        = ctypes.WINFUNCTYPE
    SetValue = F(ctypes.HRESULT, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(vtbl[6])
    Commit   = F(ctypes.HRESULT, ctypes.c_void_p)(vtbl[7])
    Release  = F(ctypes.c_ulong,  ctypes.c_void_p)(vtbl[2])

    key = PROPERTYKEY()
    ctypes.memmove(key.fmtid, _make_guid_bytes("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), 16)
    key.pid = 5  # PKEY_AppUserModel_ID pid

    # PROPVARIANT (16 bytes): vt(2) + reserved(6) + LPWSTR pointer(8)
    buf     = ctypes.create_unicode_buffer(app_id)
    buf_ptr = ctypes.cast(buf, ctypes.c_void_p).value
    pv      = (ctypes.c_byte * 16)()
    ctypes.memmove(pv,                                   ctypes.byref(ctypes.c_ushort(VT_LPWSTR)), 2)
    ctypes.memmove(ctypes.addressof(pv) + 8,            ctypes.byref(ctypes.c_void_p(buf_ptr)),   ctypes.sizeof(ctypes.c_void_p))

    try:
        hr = SetValue(ppv.value, ctypes.byref(key), pv)
        if hr != 0:
            raise OSError(f"SetValue: 0x{hr & 0xFFFFFFFF:08X}")
        hr = Commit(ppv.value)
        if hr != 0:
            raise OSError(f"Commit: 0x{hr & 0xFFFFFFFF:08X}")
    finally:
        Release(ppv.value)
        ctypes.windll.ole32.CoUninitialize()


def get_desktop() -> str:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ) as k:
            return winreg.QueryValueEx(k, "Desktop")[0]
    except Exception:
        return str(Path.home() / "Desktop")


if __name__ == "__main__":
    if sys.platform != "win32":
        print("Windows only"); sys.exit(1)

    lnk = os.path.join(get_desktop(), LNK_NAME)
    if not os.path.exists(lnk):
        print(f"ERROR: shortcut not found: {lnk}"); sys.exit(1)

    set_appusermodel_id(lnk, APP_ID)
    print(f"OK  AppUserModelID = '{APP_ID}'")
    print(f"    on {lnk}")
