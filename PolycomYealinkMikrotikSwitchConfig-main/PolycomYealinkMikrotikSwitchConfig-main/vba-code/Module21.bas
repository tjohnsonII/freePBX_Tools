Attribute VB_Name = "Module21"
Public Sub CleanExtensions()
    Dim ws As Worksheet
    Dim lastRow As Long
    Dim i As Long
    Dim rawVal As String
    Dim cleaned As String
    
    Set ws = ThisWorkbook.Sheets("DIDs") ' <-- change sheet name if needed
    lastRow = ws.Cells(ws.Rows.Count, "B").End(xlUp).row
    
    For i = 2 To lastRow ' assuming row 1 is header
        rawVal = ws.Cells(i, "B").Value
        cleaned = CleanNumber(rawVal)
        ws.Cells(i, "B").Value = cleaned
    Next i
    
    MsgBox "Extensions cleaned.", vbInformation
End Sub

Private Function CleanNumber(ByVal txt As String) As String
    Dim i As Long
    Dim ch As String
    Dim output As String
    
    For i = 1 To Len(txt)
        ch = Mid(txt, i, 1)
        If ch Like "[0-9]" Then
            output = output & ch
        End If
    Next i
    
    CleanNumber = output
End Function

