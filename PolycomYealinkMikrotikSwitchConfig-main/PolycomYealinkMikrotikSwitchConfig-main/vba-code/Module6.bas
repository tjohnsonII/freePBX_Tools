Attribute VB_Name = "Module6"
Sub ClearAllContent()
     Dim ws As Worksheet
    Set ws = ThisWorkbook.Sheets("fpbx") ' Change sheet name if needed

    ' Clear only columns A, B, C, J, and N from row 2 to 1000
    ws.Range("A2:A1000").ClearContents   ' extension
    ws.Range("B2:B1000").ClearContents   ' name
    ws.Range("C2:C1000").ClearContents   ' description
    ws.Range("J2:J1000").ClearContents   ' voicemail_email
    ws.Range("N2:N1000").ClearContents   ' outboundcid
    ws.Range("E2:E1000").ClearContents   ' secret
End Sub

