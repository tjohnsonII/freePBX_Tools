Attribute VB_Name = "Module22"
Sub ClearExtensionTableCopyUserExtensions()

    ' Adjust range as needed
    
    Dim answer As VbMsgBoxResult
    answer = MsgBox("This will clear all extension data. Continue?", _
                    vbYesNo + vbExclamation, "Confirm Clear")

    If answer = vbNo Then Exit Sub

    Dim lastRow As Long
    lastRow = Cells(Rows.Count, "A").End(xlUp).row

    If lastRow >= 2 Then
        Range("A2:G" & lastRow).ClearContents
    End If

End Sub
