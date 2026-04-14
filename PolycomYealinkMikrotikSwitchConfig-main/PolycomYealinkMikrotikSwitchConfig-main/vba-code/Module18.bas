Attribute VB_Name = "Module18"
Option Explicit
' === helper: find header col number by header text (case-insensitive, row 1) ===
Private Function GetHeaderCol(ws As Worksheet, headerText As String) As Long
    Dim c As Range
    For Each c In ws.Rows(1).Cells
        If Len(c.Value2) = 0 Then Exit For
        If LCase$(Trim$(c.Value2)) = LCase$(Trim$(headerText)) Then
            GetHeaderCol = c.Column
            Exit Function
        End If
    Next c
End Function

' === helper: generate random password ===
Private Function GeneratePassword(Optional ByVal length As Long = 8) As String
    Dim chars As String, i As Long, n As Long
    Dim sb As String

    ' Allowed characters: A-Z, a-z, 0-9, and !@#$%^&*()
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" & _
            "abcdefghijklmnopqrstuvwxyz" & _
            "0123456789" & _
            "!@#$%^&*()"

    Randomize
    For i = 1 To length
        n = Int(Len(chars) * Rnd) + 1
        sb = sb & Mid$(chars, n, 1)
    Next i

    GeneratePassword = sb
End Function



' ===== main: build stretto_import from fpbx =====
Sub PopulateStrettoFromFPBX()
    Dim wsFPX As Worksheet, wsST As Worksheet
    Dim colExt As Long, colEmail As Long, colSecret As Long
    Dim lastRowFP As Long, lastRowST As Long, outLast As Long
    Dim extVal As String, emailVal As String, secretVal As String
    Dim sipDomain As String, r As Long

    sipDomain = "pbx.example.com"           ' <-- set your real domain

    Set wsFPX = ThisWorkbook.Worksheets("fpbx")
    Set wsST = ThisWorkbook.Worksheets("stretto_import")

    colExt = GetHeaderCol(wsFPX, "extension")
    colEmail = GetHeaderCol(wsFPX, "voicemail_email")
    colSecret = GetHeaderCol(wsFPX, "secret")
    If colExt = 0 Or colEmail = 0 Or colSecret = 0 Then
        MsgBox "Couldn't find one or more headers: extension, voicemail_email, secret in fpbx.", vbExclamation
        Exit Sub
    End If

    lastRowFP = wsFPX.Cells(wsFPX.Rows.Count, colExt).End(xlUp).row
    If lastRowFP < 2 Then
        MsgBox "No data rows in fpbx.", vbInformation
        Exit Sub
    End If

    lastRowST = wsST.Cells(wsST.Rows.Count, "A").End(xlUp).row
    If lastRowST < 2 Then lastRowST = 2

    ' Always unmerge to avoid 1004 on ClearContents
    With wsST.Range("A2:I" & lastRowST)
        .UnMerge
        .ClearContents
    End With

    outLast = 1
    Application.ScreenUpdating = False

    For r = 2 To lastRowFP
        extVal = Trim(wsFPX.Cells(r, colExt).Value)
        emailVal = Trim(wsFPX.Cells(r, colEmail).Value)
        secretVal = Trim(wsFPX.Cells(r, colSecret).Value)

        If extVal <> "" Then
            outLast = outLast + 1
            wsST.Cells(outLast, "A").Value = emailVal
            wsST.Cells(outLast, "B").Value = GeneratePassword(8)
            wsST.Cells(outLast, "C").Value = emailVal
            wsST.Cells(outLast, "D").Value = "sip.only"
            wsST.Cells(outLast, "E").Value = wsFPX.Cells(2, 1).Value
            wsST.Cells(outLast, "F").Value = secretVal
            wsST.Cells(outLast, "G").Value = extVal
            wsST.Cells(outLast, "H").Value = extVal
            wsST.Cells(outLast, "I").Value = sipDomain
        End If
    Next r

    Application.ScreenUpdating = True
    MsgBox "Stretto sheet populated with " & (outLast - 1) & " row(s).", vbInformation
End Sub

Sub ApplyRowShadingRules_VPBX()
    Dim ws As Worksheet
    Dim lo As ListObject
    Dim dataRange As Range
    Dim peachRule As FormatCondition
    Dim yellowRule As FormatCondition
    Dim anchor As Range
    Dim anchorAddr As String
    Dim peachFormula As String
    Dim yellowFormula As String

    Set ws = ThisWorkbook.Sheets("vpbx")
    Set lo = ws.ListObjects("vpbxTable")

    If lo.DataBodyRange Is Nothing Then
        MsgBox "vpbxTable has no data rows.", vbInformation
        Exit Sub
    End If

    Set dataRange = lo.DataBodyRange
    dataRange.FormatConditions.Delete

    ' Use the FIRST cell in the FIRST column of the DATA BODY (never the header),
    ' and make the row reference relative so the CF shifts per row.
    Set anchor = dataRange.Columns(1).Cells(1, 1)
    anchorAddr = anchor.Address(RowAbsolute:=False, ColumnAbsolute:=True)

    peachFormula = "=LEN(" & anchorAddr & ")<>0"
    yellowFormula = "=LEN(" & anchorAddr & ")=0"

    Set peachRule = dataRange.FormatConditions.Add(Type:=xlExpression, Formula1:=peachFormula)
    With peachRule
        .Interior.Color = RGB(255, 204, 153)
        .StopIfTrue = False
    End With

    Set yellowRule = dataRange.FormatConditions.Add(Type:=xlExpression, Formula1:=yellowFormula)
    With yellowRule
        .Interior.Color = RGB(255, 255, 153)
        .StopIfTrue = False
    End With

    MsgBox "Conditional formatting applied to vpbxTable.", vbInformation
End Sub

