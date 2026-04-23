Attribute VB_Name = "Module19"
Option Explicit

'--- find a ListObject on a sheet by name (case-insensitive).
'If not found and the sheet has exactly one table, return that one.
Private Function GetTable(ws As Worksheet, wanted As String) As ListObject
    Dim lo As ListObject
    For Each lo In ws.ListObjects
        If LCase$(Trim$(lo.Name)) = LCase$(Trim$(wanted)) Then
            Set GetTable = lo
            Exit Function
        End If
    Next lo
    If ws.ListObjects.Count = 1 Then
        Set GetTable = ws.ListObjects(1)
    End If
End Function

'--- find a column in a table by header text (case-insensitive)
Private Function ColIdx(lo As ListObject, headerText As String) As Long
    Dim lc As ListColumn
    For Each lc In lo.ListColumns
        If LCase$(Trim$(lc.Name)) = LCase$(Trim$(headerText)) Then
            ColIdx = lc.Index
            Exit Function
        End If
    Next lc
End Function

Public Sub PopulateFPBX_FromCopyUsers()
    Dim wsSrc As Worksheet, wsDst As Worksheet
    Dim loSrc As ListObject, loDst As ListObject
    Dim cUser As Long, cExt As Long, cEmail As Long, cCID As Long
    Dim dExt As Long, dName As Long, dDesc As Long, dVMEmail As Long, dCID As Long
    Dim dVMPager As Long, dVMOpts As Long
    Dim needRows As Long, outRow As Long, r As Long
    Dim extVal As String, nameVal As String, emailVal As String, cidVal As String

    '--- sheets
    Set wsSrc = ThisWorkbook.Worksheets("copyUserExtensions")
    Set wsDst = ThisWorkbook.Worksheets("fpbx")

    '--- tables (case-insensitive; falls back to the only table if present)
    Set loSrc = GetTable(wsSrc, "copyUserExtensions")
    Set loDst = GetTable(wsDst, "fpbxTable")

    If loSrc Is Nothing Or loSrc.DataBodyRange Is Nothing Then
        MsgBox "No rows found in source table on 'copyUserExtensions'.", vbInformation
        Exit Sub
    End If
    If loDst Is Nothing Or loDst.DataBodyRange Is Nothing Then
        MsgBox "fpbxTable not found (or empty) on 'fpbx'.", vbCritical
        Exit Sub
    End If

    '--- source headers (as displayed in your screenshot)
    ' source column indexes (accept common variations)
    cUser = ColIdxAny(loSrc, "User Name", "Name")
    cExt = ColIdxAny(loSrc, "Extension Number", "Extension", "Ext")
    cEmail = ColIdxAny(loSrc, "Email", "Email Address")
    cCID = ColIdxAny(loSrc, "Caller ID Number (Required)", "Caller ID Number", "CallerID", "CID")


    If cUser * cExt * cEmail * cCID = 0 Then
        MsgBox "Missing one or more source headers. Needed: 'User Name', 'Extension Number', 'Email', 'Caller ID Number (Required)'.", vbCritical
        Exit Sub
    End If

    '--- destination headers in fpbxTable
    dExt = ColIdx(loDst, "extension")
    dName = ColIdx(loDst, "name")
    dDesc = ColIdx(loDst, "description")
    dVMEmail = ColIdx(loDst, "voicemail_email")
    dCID = ColIdx(loDst, "outboundcid")


    If dExt * dName * dDesc * dVMEmail * dCID = 0 Then
        MsgBox "Missing one or more destination headers on fpbxTable.", vbCritical
        Exit Sub
    End If

    '--- count nonblank extensions in source
    needRows = 0
    For r = 1 To loSrc.DataBodyRange.Rows.Count
        If Len(Trim(loSrc.DataBodyRange.Cells(r, cExt).Value)) > 0 Then
            needRows = needRows + 1
        End If
    Next r

    '--- size fpbxTable to fit
    Do While loDst.ListRows.Count < needRows
        loDst.ListRows.Add
    Loop
    Do While loDst.ListRows.Count > needRows And loDst.ListRows.Count > 1
        loDst.ListRows(loDst.ListRows.Count).Delete
    Loop

    Application.ScreenUpdating = False
    outRow = 0

    For r = 1 To loSrc.DataBodyRange.Rows.Count
        extVal = Trim(loSrc.DataBodyRange.Cells(r, cExt).Value)
        If Len(extVal) = 0 Then GoTo NextR

        nameVal = Trim(loSrc.DataBodyRange.Cells(r, cUser).Value)
        emailVal = Trim(loSrc.DataBodyRange.Cells(r, cEmail).Value)
        cidVal = Trim(loSrc.DataBodyRange.Cells(r, cCID).Value)

        outRow = outRow + 1
        ' write to fpbxTable row outRow
        loDst.DataBodyRange.Cells(outRow, dExt).Value = extVal
        loDst.DataBodyRange.Cells(outRow, dName).Value = nameVal
        loDst.DataBodyRange.Cells(outRow, dDesc).Value = nameVal          ' description = name
        loDst.DataBodyRange.Cells(outRow, dVMEmail).Value = emailVal
        loDst.DataBodyRange.Cells(outRow, dCID).Value = cidVal

        
NextR:
    Next r

    Application.ScreenUpdating = True
    MsgBox "Copied " & outRow & " row(s) from copyUserExtensions into fpbxTable." & vbCrLf & _
           "voicemail_pager and voicemail_options set to blank.", vbInformation
End Sub

'--- normalize header text for robust matching
Private Function NormalizeHeader(ByVal s As String) As String
    s = Replace(s, vbCr, " ")
    s = Replace(s, vbLf, " ")
    s = Replace(s, Chr$(160), " ")         ' non-breaking space
    s = Trim$(s)
    Do While InStr(s, "  ") > 0           ' collapse double spaces
        s = Replace(s, "  ", " ")
    Loop
    NormalizeHeader = LCase$(s)
End Function

'--- find a column by ANY of several possible header aliases
Private Function ColIdxAny(lo As ListObject, ParamArray aliases() As Variant) As Long
    Dim lc As ListColumn, a As Variant
    For Each lc In lo.ListColumns
        For Each a In aliases
            If NormalizeHeader(lc.Name) = NormalizeHeader(CStr(a)) Then
                ColIdxAny = lc.Index
                Exit Function
            End If
        Next a
    Next lc
    ColIdxAny = 0
End Function


