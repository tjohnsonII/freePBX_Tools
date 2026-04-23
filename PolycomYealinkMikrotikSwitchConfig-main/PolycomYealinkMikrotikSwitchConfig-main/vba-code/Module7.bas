Attribute VB_Name = "Module7"
Sub ClearVPBXSheet()
    Dim ws As Worksheet
    Dim lastRow As Long

    Set ws = ThisWorkbook.Sheets("vpbx")

    ' Find the last used row in column A
    lastRow = ws.Cells(ws.Rows.Count, "A").End(xlUp).row
    If lastRow < 2 Then Exit Sub  ' nothing below headers

    ' CLEAR ONLY THE COLUMNS WE WANT TO RESET
    ' mac / model / extension / name / description / secret
    ws.Range("A2:A" & lastRow).ClearContents   ' mac
    ws.Range("B2:B" & lastRow).ClearContents   ' model
    ws.Range("C2:C" & lastRow).ClearContents   ' extension
    ws.Range("D2:D" & lastRow).ClearContents   ' name
    ws.Range("E2:E" & lastRow).ClearContents   ' description
    ws.Range("F2:F" & lastRow).ClearContents   ' secret

    MsgBox "VPBX sheet cleared (kept voicemail/default columns).", vbInformation, "Done"
End Sub

