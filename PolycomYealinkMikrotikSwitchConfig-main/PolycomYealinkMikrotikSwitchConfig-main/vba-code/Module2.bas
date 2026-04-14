Attribute VB_Name = "Module2"
Sub ExportRangeToCSV()
    Dim ws As Worksheet
    Dim exportRange As Range
    Dim filePath As String
    Dim cell As Range
    Dim rowValues As String
    Dim csvContent As String
    Dim row As Range
    Dim lastRow As Long

    Set ws = ThisWorkbook.Sheets("stretto_import")

    ' Find last row with data in column A (username)
    lastRow = ws.Cells(ws.Rows.Count, "A").End(xlUp).row

    ' Include header row (A1:H1) and data rows (A2:H[lastRow])
    Set exportRange = ws.Range("A1:H" & lastRow)

    ' Ask where to save
    filePath = Application.GetSaveAsFilename( _
        InitialFileName:="exported_users.csv", _
        FileFilter:="CSV Files (*.csv), *.csv")

    If filePath = "False" Then Exit Sub ' User cancelled

    ' Build CSV content
    For Each row In exportRange.Rows
        rowValues = ""
        For Each cell In row.Cells
            rowValues = rowValues & """" & Replace(cell.Text, """", "'") & ""","
        Next cell
        ' Only include rows with content in column A and B (username and password)
        If Trim(row.Cells(1, 1).Text) <> "" And Trim(row.Cells(1, 2).Text) <> "" Then
            csvContent = csvContent & Left(rowValues, Len(rowValues) - 1) & vbCrLf
        End If
    Next row

    ' Write to file
    Dim fso As Object
    Set fso = CreateObject("Scripting.FileSystemObject")
    Dim txtStream As Object
    Set txtStream = fso.CreateTextFile(filePath, True, False)
    txtStream.Write csvContent
    txtStream.Close

    MsgBox "Data exported successfully to:" & vbCrLf & filePath, vbInformation
End Sub


