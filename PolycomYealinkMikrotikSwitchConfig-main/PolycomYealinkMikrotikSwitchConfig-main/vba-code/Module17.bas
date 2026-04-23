Attribute VB_Name = "Module17"
Option Explicit

'==========================
' HELPER: random secret
'==========================
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

'==========================
' INTERNAL: are all required fields filled?
' We only want to generate a secret for rows that are “real”
' i.e. extension, name, description, outboundcid are not blank.
'==========================
Private Function RowIsComplete(extVal As String, nm As String, desc As String, outboundVal As String) As Boolean
    RowIsComplete = (Len(extVal) > 0 And Len(nm) > 0 And Len(desc) > 0 And Len(outboundVal) > 0)
End Function

'==========================
' TABLE-AWARE SECRET GENERATOR
' Populates the [secret] column ONLY where:
'   - row looks complete, AND
'   - secret is currently blank
'==========================
Sub GenerateSecrets_Table()
    Dim ws As Worksheet
    Dim lo As ListObject
    Dim r As Long, rowCount As Long
    Dim extVal As String, nm As String, descVal As String
    Dim outboundVal As String
    Dim tgt As Range
    Dim filled As Long

    ' 1. Get table
    Set ws = ThisWorkbook.Sheets("fpbx")
    Set lo = ws.ListObjects("fpbxTable")

    ' 2. How many populated rows does the table currently have?
    '    DataBodyRange is JUST the rows under the headers (no extra blank rows on the sheet)
    If lo.DataBodyRange Is Nothing Then
        MsgBox "No data rows in fpbxTable.", vbInformation
        Exit Sub
    End If
    rowCount = lo.DataBodyRange.Rows.Count

    ' 3. Loop each data row in the table
    ' NOTE: DataBodyRange.Rows(1) corresponds to sheet row 2 (first data row).
    For r = 1 To rowCount

        extVal = Trim(lo.ListColumns("extension").DataBodyRange.Cells(r, 1).Value)
        nm = Trim(lo.ListColumns("name").DataBodyRange.Cells(r, 1).Value)
        descVal = Trim(lo.ListColumns("description").DataBodyRange.Cells(r, 1).Value)
        outboundVal = Trim(lo.ListColumns("outboundcid").DataBodyRange.Cells(r, 1).Value)

        ' Only proceed on a "real" row, based on your rule:
        If RowIsComplete(extVal, nm, descVal, outboundVal) Then

            Set tgt = lo.ListColumns("secret").DataBodyRange.Cells(r, 1)
            If Len(tgt.Value) = 0 Then
                tgt.Value = GenerateSecret(32)
                filled = filled + 1
            End If

        End If
    Next r

    MsgBox "Generated " & filled & " secret(s) using fpbxTable.", vbInformation
End Sub


'==========================
' TABLE-AWARE POPULATOR
' Mirrors your PopulateFPBXFields macro, but writes into the table columns
' instead of raw sheet cells.
'
' Logic:
'   - tech                = "pjsip"
'   - secret              (leave whatever is there; do not overwrite)
'   - callwaiting_enable  = "ENABLED"
'   - voicemail           = "default"
'   - voicemail_enable    = "yes"
'   - voicemail_vmpwd     = "123" & extension
'   - voicemail_email     = keep existing data in table
'   - voicemail_pager     = "off"
'   - voicemail_options   = attach=yes|... if email present, else attach=no|...
'   - voicemail_same_exten= "no"
'   - outboundcid         = (keep whatever user typed)
'   - id                  = extension
'   - dial                = "PJSIP/" & extension
'   - user                = extension
'   - max_contacts        = 10
'   - accountcode         = extension
'==========================
Sub PopulateFPBXFields_Table()
    Dim ws As Worksheet
    Dim lo As ListObject
    Dim r As Long, rowCount As Long
    Dim extVal As String, emailVal As String, outCID As String

    Set ws = ThisWorkbook.Sheets("fpbx")
    Set lo = ws.ListObjects("fpbxTable")

    If lo.DataBodyRange Is Nothing Then
        MsgBox "No data rows in fpbxTable.", vbInformation
        Exit Sub
    End If

    rowCount = lo.DataBodyRange.Rows.Count

    For r = 1 To rowCount
        extVal = Trim(lo.ListColumns("extension").DataBodyRange.Cells(r, 1).Value)
        emailVal = Trim(lo.ListColumns("voicemail_email").DataBodyRange.Cells(r, 1).Value)
        outCID = Trim(lo.ListColumns("outboundcid").DataBodyRange.Cells(r, 1).Value)

        If Len(extVal) > 0 Then
            lo.ListColumns("tech").DataBodyRange.Cells(r, 1).Value = "pjsip"
            lo.ListColumns("callwaiting_enable").DataBodyRange.Cells(r, 1).Value = "ENABLED"
            lo.ListColumns("voicemail").DataBodyRange.Cells(r, 1).Value = "default"
            lo.ListColumns("voicemail_enable").DataBodyRange.Cells(r, 1).Value = "yes"
            lo.ListColumns("voicemail_vmpwd").DataBodyRange.Cells(r, 1).Value = "123" & extVal

           

            lo.ListColumns("voicemail_same_exten").DataBodyRange.Cells(r, 1).Value = "no"
            ' keep whatever is in outboundcid (no overwrite)

            lo.ListColumns("id").DataBodyRange.Cells(r, 1).Value = extVal
            lo.ListColumns("dial").DataBodyRange.Cells(r, 1).Value = "PJSIP/" & extVal
            lo.ListColumns("user").DataBodyRange.Cells(r, 1).Value = extVal
            lo.ListColumns("max_contacts").DataBodyRange.Cells(r, 1).Value = 10
            lo.ListColumns("accountcode").DataBodyRange.Cells(r, 1).Value = extVal
        End If
    Next r

    MsgBox "fpbxTable populated.", vbInformation
End Sub

Sub ApplyRowShadingRules_Table()
    Dim ws As Worksheet
    Dim lo As ListObject
    Dim dataRange As Range
    Dim peachRule As FormatCondition
    Dim yellowRule As FormatCondition
    Dim firstDataRow As Long
    Dim firstDataCol As Long
    Dim addr As String
    
    Set ws = ThisWorkbook.Sheets("fpbx")
    Set lo = ws.ListObjects("fpbxTable")
    
    ' If there are no rows in the table, bail
    If lo.DataBodyRange Is Nothing Then
        MsgBox "fpbxTable has no data rows yet.", vbInformation
        Exit Sub
    End If
    
    ' We'll apply formatting to the entire data region of the table (not header)
    Set dataRange = lo.DataBodyRange
    
    ' Clear any existing conditional formats on that range first
    dataRange.FormatConditions.Delete
    
    ' We need to build formulas that point to the extension column
    ' We'll anchor the row test on the first column of the table
    ' Example formula in Excel for peach:
    '   =LEN($A2)<>0
    '
    ' We can't hardcode "A2" because maybe your table isn't in A.
    ' So we'll calculate the absolute column letter of the table's first column.
    
    firstDataRow = dataRange.row         ' e.g. 2
    firstDataCol = dataRange.Column      ' e.g. 1 for column A
    
    ' Build something like "$A2" or "$D5" depending on where the table starts
    Dim firstColLetter As String
    firstColLetter = Split(ws.Cells(1, firstDataCol).Address(True, False), "$")(0)
        ' Explanation:
        '   ws.Cells(1, firstDataCol).Address(True, False) -> "$A$1"
        '   Split(...,"$")(0) -> "" (blank)
        '   Split(...,"$")(1) -> "A"
        ' We actually want the column letter only.
    firstColLetter = Split(ws.Cells(1, firstDataCol).Address(False, False), "$")(0)
        ' ws.Cells(1, firstDataCol).Address(False, False) -> "A1"
        ' Split(...,"$")(0) -> "A1"
        ' Now strip the row number:
    firstColLetter = Replace(firstColLetter, ws.Cells(1, firstDataCol).row, "")
        ' becomes "A" (or "D", etc.)
    
    ' Now construct the formulas using that first column letter and the FIRST data row number.
    ' Peach (row active): LEN($A2)<>0
    ' Yellow (row empty): LEN($A2)=0
    Dim peachFormula As String
    Dim yellowFormula As String
    
    peachFormula = "=LEN($" & firstColLetter & firstDataRow & ")<>0"
    yellowFormula = "=LEN($" & firstColLetter & firstDataRow & ")=0"
    
    ' Add PEACH rule first (active rows)
    Set peachRule = dataRange.FormatConditions.Add( _
        Type:=xlExpression, _
        Formula1:=peachFormula)
    With peachRule
        .Interior.Color = RGB(255, 204, 153) ' peach-ish
        .StopIfTrue = False
    End With
    
    ' Add YELLOW rule second (empty / template rows)
    Set yellowRule = dataRange.FormatConditions.Add( _
        Type:=xlExpression, _
        Formula1:=yellowFormula)
    With yellowRule
        .Interior.Color = RGB(255, 255, 153) ' light yellow
        .StopIfTrue = False
    End With
    
    MsgBox "Conditional formatting applied to fpbxTable body.", vbInformation
End Sub

Sub MirrorFPBXtoVPBX_NoMacNoModel_Debug()
    Dim wsFP As Worksheet, wsVP As Worksheet
    Dim loFP As ListObject, loVP As ListObject
    Dim keepCols As Collection, c As ListColumn
    Dim tmpData As Variant, outData() As Variant
    Dim r As Long, i As Long, k As Long
    Dim lastRow As Long, keepCount As Long
    
    On Error GoTo ErrHandler
    MsgBox "Step 1: Starting macro...", vbInformation
    
    Set wsFP = ThisWorkbook.Sheets("fpbx")
    Set wsVP = ThisWorkbook.Sheets("vpbx")
    MsgBox "Step 2: Sheets found."
    
    Set loFP = wsFP.ListObjects("fpbxTable")
    Set loVP = wsVP.ListObjects("vpbxTable")
    MsgBox "Step 3: Tables found."
    
    If loFP.DataBodyRange Is Nothing Then
        MsgBox "fpbxTable is empty.", vbExclamation
        Exit Sub
    End If
    
    ' Build list of columns to copy
    Set keepCols = New Collection
    For Each c In loFP.ListColumns
        Select Case LCase(Trim(c.Name))
            Case "mac", "model"
                ' skip
            Case Else
                keepCols.Add c.Index
        End Select
    Next c
    
    keepCount = keepCols.Count
    MsgBox "Step 4: Columns to copy: " & keepCount
    
    tmpData = loFP.DataBodyRange.Value
    ReDim outData(1 To UBound(tmpData, 1), 1 To keepCount)
    
    For r = 1 To UBound(tmpData, 1)
        k = 1
        For i = 1 To keepCols.Count
            outData(r, k) = tmpData(r, keepCols(i))
            k = k + 1
        Next i
    Next r
    
    MsgBox "Step 5: Built output array with " & UBound(outData, 1) & " rows."
    
    ' Find first data cell in vpbx table
    Dim dest As Range
    Set dest = loVP.DataBodyRange.Cells(1, 1)
    
    ' Clear current data
    loVP.DataBodyRange.ClearContents
    MsgBox "Step 6: Cleared vpbx data range."
    
    ' Paste into vpbx
    dest.Resize(UBound(outData, 1), UBound(outData, 2)).Value = outData
    MsgBox "? Step 7: Data copied successfully to vpbxTable (" & UBound(outData, 1) & " rows)."
    
    ' Optional: reapply formatting automatically
    Call ApplyRowShadingRules_VPBX
    
    Exit Sub

ErrHandler:
    MsgBox "? Error: " & Err.Description, vbCritical
End Sub


' helper: get the column index in a table by header name (case-insensitive)
Private Function GetColumnIndexByHeader(lo As ListObject, headerName As String) As Long
    Dim lc As ListColumn
    For Each lc In lo.ListColumns
        If LCase$(Trim$(lc.Name)) = LCase$(Trim$(headerName)) Then
            GetColumnIndexByHeader = lc.Index
            Exit Function
        End If
    Next lc
End Function

' helper: get a value from a given table row r and header name
Private Function GetValueByHeader(lo As ListObject, rowNum As Long, headerName As String) As Variant
    Dim ColIdx As Long
    ColIdx = GetColumnIndexByHeader(lo, headerName)
    If ColIdx > 0 Then
        GetValueByHeader = lo.DataBodyRange.Cells(rowNum, ColIdx).Value
    Else
        GetValueByHeader = ""
    End If
End Function


Sub ApplyRowShadingRules_VPBX()
    Dim ws As Worksheet
    Dim lo As ListObject
    Dim dataRange As Range
    Dim peachRule As FormatCondition
    Dim yellowRule As FormatCondition
    Dim firstDataRow As Long
    Dim firstDataCol As Long
    Dim firstColLetter As String
    Dim peachFormula As String
    Dim yellowFormula As String

    '--- point to vpbx sheet + table
    Set ws = ThisWorkbook.Sheets("vpbx")
    Set lo = ws.ListObjects("vpbxTable")

    '--- sanity check
    If lo.DataBodyRange Is Nothing Then
        MsgBox "vpbxTable has no data rows.", vbInformation
        Exit Sub
    End If

    Set dataRange = lo.DataBodyRange
    dataRange.FormatConditions.Delete

    '--- determine first data row & col
    firstDataRow = dataRange.row
    firstDataCol = dataRange.Column

    '--- derive first column letter (for formula reference)
    firstColLetter = Replace(ws.Cells(1, firstDataCol).Address(False, False), ws.Cells(1, firstDataCol).row, "")
    ' now e.g. "A"

    '--- build conditional formulas
    ' we’ll anchor to first column (extension)
    peachFormula = "=LEN($" & firstColLetter & firstDataRow & ")<>0"
    yellowFormula = "=LEN($" & firstColLetter & firstDataRow & ")=0"

    '--- peach rule = active rows
    Set peachRule = dataRange.FormatConditions.Add(Type:=xlExpression, Formula1:=peachFormula)
    With peachRule
        .Interior.Color = RGB(255, 204, 153)  ' peach
        .StopIfTrue = False
    End With

    '--- yellow rule = empty rows
    Set yellowRule = dataRange.FormatConditions.Add(Type:=xlExpression, Formula1:=yellowFormula)
    With yellowRule
        .Interior.Color = RGB(255, 255, 153)  ' light yellow
        .StopIfTrue = False
    End With

    MsgBox "Conditional formatting applied to vpbxTable.", vbInformation
End Sub



' Generate a random 12-hex-digit MAC (no separators)
Private Function MakeMac12() As String
    Dim hexChars As String
    Dim i As Long
    Dim outMac As String

    hexChars = "0123456789ABCDEF"

    For i = 1 To 12
        outMac = outMac & Mid$(hexChars, Int(Rnd() * 16) + 1, 1)
    Next i

    MakeMac12 = outMac
End Function

Public Sub GenerateMACs_SheetMode()
    Dim ws As Worksheet
    Dim headerRow As Long
    Dim macCol As Long
    Dim modelCol As Long
    Dim lastRow As Long
    Dim r As Long
    Dim filled As Long

    Set ws = ThisWorkbook.Worksheets("vpbx")

    ' we assume headers are in row 1 like in your screenshot
    headerRow = 1

    ' find columns by header text
    macCol = FindColumnByHeader(ws, headerRow, "mac")
    modelCol = FindColumnByHeader(ws, headerRow, "model")

    If macCol = 0 Then
        MsgBox "Couldn't find a header called 'mac' in row " & headerRow & " on '" & ws.Name & "'.", vbExclamation
        Exit Sub
    End If

    If modelCol = 0 Then
        MsgBox "Couldn't find a header called 'model' in row " & headerRow & " on '" & ws.Name & "'.", vbExclamation
        Exit Sub
    End If

    ' figure out the last row to process:
    ' we'll use the model column as the "anchor", because you pick a model for each phone/row
    lastRow = ws.Cells(ws.Rows.Count, modelCol).End(xlUp).row
    If lastRow <= headerRow Then
        MsgBox "No data rows found under the headers on '" & ws.Name & "'.", vbInformation
        Exit Sub
    End If

    Application.ScreenUpdating = False
    Randomize

    For r = headerRow + 1 To lastRow
        ' only generate if:
        '   - model cell is not blank (row actually in use)
        '   - mac is blank (we haven't filled it yet)
        If Trim(ws.Cells(r, modelCol).Value2) <> "" Then
            If Trim(ws.Cells(r, macCol).Value2) = "" Then
                ws.Cells(r, macCol).Value = MakeMac12()
                filled = filled + 1
            End If
        End If
    Next r

    Application.ScreenUpdating = True

    MsgBox "Generated " & filled & " MAC(s) on '" & ws.Name & "'.", vbInformation
End Sub

' Tiny helper to locate "mac", "model", etc. in row 1
Private Function FindColumnByHeader(ws As Worksheet, headerRow As Long, headerText As String) As Long
    Dim c As Range
    For Each c In ws.Rows(headerRow).Cells
        If Trim(LCase$(c.Value2)) = Trim(LCase$(headerText)) Then
            FindColumnByHeader = c.Column
            Exit Function
        End If
        ' stop if we run off into empty cells to the right
        If Len(c.Value2) = 0 And c.Column > 200 Then
            Exit For
        End If
    Next c
End Function




' === Helper: find header by name (case-insensitive, row 1 only) ===
Private Function FindHeaderCol(ws As Worksheet, headerText As String) As Long
    Dim c As Range
    For Each c In ws.Rows(1).Cells
        If Len(c.Value2) = 0 Then Exit For
        If LCase$(Trim(c.Value2)) = LCase$(Trim(headerText)) Then
            FindHeaderCol = c.Column
            Exit Function
        End If
    Next c
End Function


' === Helper: generate a unique, uppercase 12-digit MAC ===
Private Function GenerateRandomMAC() As String
    Dim i As Integer
    Dim hexChars As String
    Dim mac As String
    hexChars = "0123456789ABCDEF"
    
    For i = 1 To 12
        mac = mac & Mid$(hexChars, Int(Rnd() * 16) + 1, 1)
        If i Mod 2 = 0 And i < 12 Then mac = mac & ":"
    Next i
    
    GenerateRandomMAC = mac
End Function

