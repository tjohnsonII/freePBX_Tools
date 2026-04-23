Attribute VB_Name = "Module5"
Sub CleanMACColumn()
    Dim cell As Range, i As Long, ch As String, cleaned As String
    For Each cell In Range("A2:A100")
        cleaned = ""
        For i = 1 To Len(cell.Value)
            ch = Mid(cell.Value, i, 1)
            If ch Like "[0-9A-Fa-f]" Then
                cleaned = cleaned & UCase(ch)
            End If
        Next i
        cell.Value = cleaned
    Next cell
    MsgBox "MACs cleaned to 12-digit format.", vbInformation
End Sub

