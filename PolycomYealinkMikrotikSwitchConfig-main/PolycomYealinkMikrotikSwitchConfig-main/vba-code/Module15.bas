Attribute VB_Name = "Module15"
Option Explicit

' --- Strong random secret ---
Function GenerateSecret(Optional length As Long = 32) As String
    Dim chars As String
    Dim i As Long, n As Long
    Dim s As String

    ' hex charset: 0-9 + a-f
    chars = "0123456789abcdef"

    Randomize
    For i = 1 To length
        n = Int(Rnd() * Len(chars)) + 1
        s = s & Mid$(chars, n, 1)
    Next i

    GenerateSecret = s
End Function

' --- Find a header (case-insensitive) in row 1 ---
Private Function FindHeaderCol(ws As Worksheet, headerText As String) As Long
    Dim c As Range
    For Each c In ws.Rows(1).Cells
        If Len(c.Value2) = 0 Then Exit For ' stop when header row ends
        If LCase$(Trim$(c.Value2)) = LCase$(Trim$(headerText)) Then
            FindHeaderCol = c.Column
            Exit Function
        End If
    Next c
End Function

' --- Generate secrets on the ACTIVE sheet (the sheet the button lives on) ---
Sub GenerateSecrets()
    Dim ws As Worksheet
    Dim colSecret As Long, colKey As Long
    Dim lastRow As Long, i As Long
    Dim filled As Long

    Set ws = ActiveSheet  ' <- writes to the sheet you’re looking at

    ' Find columns by header
    colSecret = FindHeaderCol(ws, "secret")
    If colSecret = 0 Then
        MsgBox "Couldn't find a header named 'secret' in row 1 of sheet '" & ws.Name & "'.", vbExclamation
        Exit Sub
    End If

    ' Use "extension" as the anchor column if present, else fall back to column A
    colKey = FindHeaderCol(ws, "extension")
    If colKey = 0 Then colKey = 1

    lastRow = ws.Cells(ws.Rows.Count, colKey).End(xlUp).row
    If lastRow < 2 Then
        MsgBox "No data rows found under the headers on '" & ws.Name & "'.", vbInformation
        Exit Sub
    End If

    Application.ScreenUpdating = False
    For i = 2 To lastRow
        If Len(ws.Cells(i, colKey).Value2) > 0 Then          ' row is in use
            If Len(ws.Cells(i, colSecret).Value2) = 0 Then    ' only fill blanks
                ws.Cells(i, colSecret).Value = GenerateSecret(32)
                filled = filled + 1
            End If
        End If
    Next i
    Application.ScreenUpdating = True

    MsgBox "Generated " & filled & " secret(s) in '" & ws.Name & "'.", vbInformation
End Sub


