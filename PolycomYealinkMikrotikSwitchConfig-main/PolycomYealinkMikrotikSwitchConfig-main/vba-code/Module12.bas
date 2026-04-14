Attribute VB_Name = "Module12"
Sub ExportFullyCompleteRows()
    Dim ws As Worksheet
    Dim exportWs As Worksheet
    Dim filePath As String
    Dim lastRow As Long, lastCol As Long
    Dim i As Long, j As Long
    Dim exportRow As Long
    Dim cell As Range
    Dim isComplete As Boolean

    Set ws = ThisWorkbook.Sheets("stretto_import") ' Or ActiveSheet
    Application.ScreenUpdating = False

    ' Create temp export sheet
    Set exportWs = ThisWorkbook.Sheets.Add(After:=ws)
    exportWs.Name = "Stretto_Export_Temp"

    ' Find last used row and column
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).row
    lastCol = ws.Cells(1, ws.Columns.Count).End(xlToLeft).Column

    ' Copy headers
    ws.Range(ws.Cells(1, 1), ws.Cells(1, lastCol)).Copy Destination:=exportWs.Range("A1")
    exportRow = 2

    ' Loop through rows starting from row 2
    For i = 2 To lastRow
        isComplete = True
        For j = 1 To lastCol
            If Trim(ws.Cells(i, j).Value) = "" Then
                isComplete = False
                Exit For
            End If
        Next j

        If isComplete Then
            ws.Range(ws.Cells(i, 1), ws.Cells(i, lastCol)).Copy Destination:=exportWs.Cells(exportRow, 1)
            exportRow = exportRow + 1
        End If
    Next i

    ' Prompt to save
    filePath = Application.GetSaveAsFilename("Stretto_Cleaned.csv", "CSV Files (*.csv), *.csv")
    If filePath <> "False" Then
        exportWs.Copy
        With ActiveWorkbook
            .SaveAs Filename:=filePath, FileFormat:=xlCSV
            .Close SaveChanges:=False
        End With
        MsgBox "? CSV export complete. Only rows with all required values included.", vbInformation
    End If

    ' Cleanup
    Application.DisplayAlerts = False
    exportWs.Delete
    Application.DisplayAlerts = True
    Application.ScreenUpdating = True
End Sub

