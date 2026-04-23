Attribute VB_Name = "Module20"
Option Explicit

' Return last used row based on nonblank in column A (cidnum)
Private Function LastRow_DIDs(ws As Worksheet) As Long
    LastRow_DIDs = ws.Cells(ws.Rows.Count, "A").End(xlUp).row
End Function

' Clear only extension (B), destination (C), description (F)
Public Sub ClearDIDs()
    Dim ws As Worksheet, lastRow As Long
    Set ws = ThisWorkbook.Worksheets("DIDs")

    lastRow = LastRow_DIDs(ws)
    If lastRow < 2 Then
        MsgBox "No data to clear on DIDs.", vbInformation
        Exit Sub
    End If

    Application.ScreenUpdating = False
    ws.Range("B2:B" & lastRow).ClearContents  ' extension
    ws.Range("C2:C" & lastRow).ClearContents  ' destination
    ws.Range("F2:F" & lastRow).ClearContents  ' description
    Application.ScreenUpdating = True
End Sub

' Export A:O (headers + rows) to CSV up to lastRow — prompts for save location
Public Sub ExportDIDsToCSV()
    Dim ws As Worksheet, lastRow As Long, tmpWB As Workbook
    Dim exportRange As Range, fn As Variant

    Set ws = ThisWorkbook.Worksheets("DIDs")
    lastRow = LastRow_DIDs(ws)
    If lastRow < 2 Then
        MsgBox "No rows to export.", vbExclamation
        Exit Sub
    End If

    ' Range to export (A:O)
    Set exportRange = ws.Range("A1:O" & lastRow)

    ' Copy to a temp workbook so we can save clean CSV
    exportRange.Copy
    Set tmpWB = Application.Workbooks.Add(xlWBATWorksheet)
    tmpWB.Worksheets(1).Range("A1").PasteSpecial xlPasteValues
    Application.CutCopyMode = False

    ' Prompt user for save location
    fn = Application.GetSaveAsFilename( _
        InitialFileName:="DIDs_" & Format(Now, "yyyymmdd_hhnnss") & ".csv", _
        FileFilter:="CSV Files (*.csv), *.csv", _
        Title:="Save DIDs CSV File As")

    ' If user cancels, exit gracefully
    If fn = False Then
        tmpWB.Close SaveChanges:=False
        Exit Sub
    End If

    ' Save the file
    Application.DisplayAlerts = False
    tmpWB.SaveAs Filename:=fn, FileFormat:=xlCSVUTF8
    tmpWB.Close SaveChanges:=False
    Application.DisplayAlerts = True

    MsgBox "Exported successfully to:" & vbCrLf & fn, vbInformation
End Sub


