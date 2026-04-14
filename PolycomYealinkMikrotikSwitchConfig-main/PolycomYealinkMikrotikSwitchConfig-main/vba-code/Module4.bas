Attribute VB_Name = "Module4"
Sub CleanOutboundCIDColumn()
    Dim cell As Range
    Dim rawVal As String
    Dim cleanVal As String
    Dim ch As String
    Dim i As Integer

    For Each cell In Range("P2:P100")
        rawVal = cell.Value
        cleanVal = ""

        For i = 1 To Len(rawVal)
            ch = Mid(rawVal, i, 1)
            If ch Like "#" Then
                cleanVal = cleanVal & ch
            End If
        Next i

        cell.Value = cleanVal
    Next cell

    MsgBox "All outboundcid values cleaned in Column P.", vbInformation
End Sub

