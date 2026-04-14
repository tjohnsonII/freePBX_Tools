Attribute VB_Name = "Module10"
Sub ExportSheetAsCSV()
    Dim ws As Worksheet, tempWS As Worksheet
    Dim filePath As String
    Dim lastRow As Long, lastCol As Long
    Dim i As Long, r As Long
    Dim rng As Range
    
    ' Source sheet
    Set ws = ThisWorkbook.Sheets("fpbx")
    
    ' Prompt user for save location
    filePath = Application.GetSaveAsFilename(InitialFileName:=ws.Name & ".csv", _
        FileFilter:="CSV Files (*.csv), *.csv", Title:="Export as CSV")
    If filePath = "False" Then Exit Sub
    
    ' Find the used range
    lastRow = ws.Cells(ws.Rows.Count, "A").End(xlUp).row
    lastCol = ws.Cells(1, ws.Columns.Count).End(xlToLeft).Column
    
    ' Add a temporary sheet
    Set tempWS = ThisWorkbook.Sheets.Add
    
    r = 1
    ' Copy the header row first
    ws.Rows(1).Resize(1, lastCol).Copy Destination:=tempWS.Rows(r)
    r = r + 1
    
    ' Loop through rows and only copy rows that are completely full
    For i = 2 To lastRow
        Set rng = ws.Range(ws.Cells(i, 1), ws.Cells(i, lastCol))
        If Application.WorksheetFunction.CountBlank(rng) = 0 Then
            rng.Copy Destination:=tempWS.Rows(r)
            r = r + 1
        End If
    Next i
    
    ' Export the temp sheet
    tempWS.Copy
    With ActiveWorkbook
        .SaveAs Filename:=filePath, FileFormat:=xlCSV, CreateBackup:=False
        .Close SaveChanges:=False
    End With
    
    ' Clean up
    Application.DisplayAlerts = False
    tempWS.Delete
    Application.DisplayAlerts = True
    
    MsgBox "CSV exported successfully with only fully filled rows!", vbInformation
End Sub


