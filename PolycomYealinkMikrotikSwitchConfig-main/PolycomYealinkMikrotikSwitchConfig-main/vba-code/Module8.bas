Attribute VB_Name = "Module8"
Sub UploadVPBXToWebApp()
    On Error GoTo ErrHandler

    ' Save workbook as a temporary local file
    Dim tempPath As String
    tempPath = Environ$("TEMP") & "\vpbx_upload.xlsm"
    ThisWorkbook.SaveCopyAs tempPath

    ' Create multipart form-data body
    Dim boundary As String
    boundary = "----WebKitFormBoundary" & Format(Now, "yyyymmddhhmmss")

    Dim preamble As String
    preamble = "--" & boundary & vbCrLf
    preamble = preamble & "Content-Disposition: form-data; name=""file""; filename=""vpbx_upload.xlsm""" & vbCrLf
    preamble = preamble & "Content-Type: application/vnd.ms-excel.sheet.macroEnabled.12" & vbCrLf & vbCrLf

    Dim postamble As String
    postamble = vbCrLf & "--" & boundary & "--" & vbCrLf

    ' Convert strings to byte arrays
    Dim preBytes() As Byte, postBytes() As Byte
    preBytes = StrConv(preamble, vbFromUnicode)
    postBytes = StrConv(postamble, vbFromUnicode)

    ' Load file into byte array
    Dim fileStream As Object
    Set fileStream = CreateObject("ADODB.Stream")
    fileStream.Type = 1
    fileStream.Open
    fileStream.LoadFromFile tempPath
    Dim fileBytes() As Byte
    fileBytes = fileStream.Read
    fileStream.Close

    ' Combine all parts into final payload
    Dim totalLen As Long
    totalLen = UBound(preBytes) + 1 + UBound(fileBytes) + 1 + UBound(postBytes) + 1
    Dim postData() As Byte
    ReDim postData(0 To totalLen - 1)

    Dim i As Long, offset As Long
    For i = 0 To UBound(preBytes)
        postData(offset) = preBytes(i): offset = offset + 1
    Next
    For i = 0 To UBound(fileBytes)
        postData(offset) = fileBytes(i): offset = offset + 1
    Next
    For i = 0 To UBound(postBytes)
        postData(offset) = postBytes(i): offset = offset + 1
    Next

    ' List of fallback endpoints
    Dim urls As Variant
    urls = Array( _
        "http://localhost:5000/upload/vpbx", _
        "http://192.168.254.253:5000/upload/vpbx", _
        "http://192.168.1.60:5000/upload/vpbx", _
        "https://123hostedtools.com/upload/vpbx" _
    )

    Dim http As Object
    Set http = CreateObject("WinHttp.WinHttpRequest.5.1")

    Dim success As Boolean: success = False
    Dim urlUsed As String

    For i = LBound(urls) To UBound(urls)
        On Error Resume Next
        http.Open "POST", urls(i), False
        http.setRequestHeader "Content-Type", "multipart/form-data; boundary=" & boundary
        http.Send postData
        If http.Status = 200 Then
            success = True
            urlUsed = urls(i)
            Exit For
        End If
        On Error GoTo 0
    Next i

    If success Then
        MsgBox "VPBX upload succeeded to: " & urlUsed & vbCrLf & http.ResponseText
    Else
        MsgBox "ERROR: Upload failed to all endpoints"
    End If
    Exit Sub

ErrHandler:
    MsgBox "ERROR: " & Err.Description
End Sub


