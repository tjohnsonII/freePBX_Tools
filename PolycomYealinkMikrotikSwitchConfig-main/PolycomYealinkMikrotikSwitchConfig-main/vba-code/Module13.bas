Attribute VB_Name = "Module13"
Sub CleanColumnL()
    Dim rng As Range, cell As Range
    Dim cleaned As String
    Dim i As Long, ch As String
    
    ' Adjust the range if needed
    Set rng = Range("L2:L" & Cells(Rows.Count, "L").End(xlUp).row)
    
    For Each cell In rng
        If Not IsEmpty(cell.Value) Then
            cleaned = ""
            For i = 1 To Len(cell.Value)
                ch = Mid(cell.Value, i, 1)
                If ch Like "[0-9]" Then
                    cleaned = cleaned & ch
                End If
            Next i
            cell.Value = cleaned
        End If
    Next cell
End Sub

