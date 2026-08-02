Dim WshShell, fso, shortcut
Dim root, winPython, iconPath, scriptPath, desktopPath, shortcutPath

Set WshShell = CreateObject("WScript.Shell")
Set fso     = CreateObject("Scripting.FileSystemObject")

' scripts\ is one level below repo root
root = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(root)

winPython = "E:\DevTools\Python\pythonw.exe"
If Not fso.FileExists(winPython) Then
    MsgBox "Cannot find " & winPython & vbCrLf & _
           "Edit scripts\create_shortcut.vbs and set the correct path.", _
           16, "Scrape Manager Setup"
    WScript.Quit 1
End If

iconPath     = root & "\assets\123net.ico"
scriptPath   = root & "\scrape_gui.py"
desktopPath  = WshShell.SpecialFolders("Desktop")
shortcutPath = desktopPath & "\Scrape Manager.lnk"

Set shortcut = WshShell.CreateShortcut(shortcutPath)
shortcut.TargetPath       = winPython
shortcut.Arguments        = Chr(34) & scriptPath & Chr(34)
shortcut.WorkingDirectory = root
shortcut.Description      = "Scrape Manager - FreePBX Tools"
shortcut.IconLocation     = iconPath & ",0"
shortcut.WindowStyle      = 1
shortcut.Save()

MsgBox "Shortcut created!" & vbCrLf & vbCrLf & _
       "Next steps:" & vbCrLf & _
       "  1. Unpin the old taskbar icon (right-click -> Unpin)" & vbCrLf & _
       "  2. Right-click the new desktop shortcut -> Pin to taskbar", _
       64, "Scrape Manager Setup"
