Attribute VB_Name = "Module11"
Sub ExportVPBX_WithMAC_Debug()
    Dim ws As Worksheet
    Dim exportWs As Worksheet
    Dim filePath As String
    Dim i As Long, exportRow As Long
    Dim lastRow As Long

    On Error GoTo ErrHandler
    MsgBox "Starting macro..."

    Set ws = ThisWorkbook.Sheets("vpbx") ' CHANGE THIS IF NEEDED
    MsgBox "Working on sheet: " & ws.Name

    Application.ScreenUpdating = False
    Set exportWs = ThisWorkbook.Sheets.Add(After:=ws)
    exportWs.Name = "VPBXExportTemp"

    lastRow = ws.Cells(ws.Rows.Count, "A").End(xlUp).row
    MsgBox "Last row in column A: " & lastRow

    ws.Range("A1:U1").Copy Destination:=exportWs.Range("A1")
    exportRow = 2

    For i = 2 To lastRow
        If Trim(ws.Cells(i, "A").Value) <> "" Then
            ws.Range("A" & i & ":U" & i).Copy Destination:=exportWs.Range("A" & exportRow)
            exportRow = exportRow + 1
        End If
    Next i

    filePath = Application.GetSaveAsFilename("FilteredVPBXExport.csv", "CSV Files (*.csv), *.csv")
    If filePath <> "False" Then
        exportWs.Copy
        With ActiveWorkbook
            .SaveAs Filename:=filePath, FileFormat:=xlCSV
            .Close SaveChanges:=False
        End With
        MsgBox "? Export complete.", vbInformation
    End If

    Application.DisplayAlerts = False
    exportWs.Delete
    Application.DisplayAlerts = True
    Application.ScreenUpdating = True
    Exit Sub

ErrHandler:
    MsgBox "? Error: " & Err.Description
End Sub

