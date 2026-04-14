Attribute VB_Name = "Module1"
Sub ClearAll_Button()
    Dim ws As Worksheet
    Set ws = ThisWorkbook.Sheets("stretto_import")
    ws.Range("A2:H100").ClearContents
    
End Sub
