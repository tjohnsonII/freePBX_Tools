Attribute VB_Name = "Module9"
Sub UploadFreePBXToWebApp()
    On Error GoTo ErrHandler

    ' Save the workbook to a temporary file
    Dim tempPath As String
    tempPath = Environ$("TEMP") & "\freepbx_upload.xlsm"
    ThisWorkbook.SaveCopyAs tempPath

    ' Define multipart form-data boundary and headers
    Dim boundary As String
    boundary = "----WebKitFormBoundary" & Format(Now, "yyyymmddhhmmss")

    Dim preamble As String
    preamble = "--" & boundary & vbCrLf
    preamble = preamble & "Content-Disposition: form-data; name=""file""; filename=""freepbx_upload.xlsm""" & vbCrLf
    preamble = preamble & "Content-Type: application/vnd.ms-excel.sheet.macroEnabled.12" & vbCrLf & vbCrLf

    Dim postamble As String
    postamble = vbCrLf & "--" & boundary & "--" & vbCrLf

    ' Convert string parts to byte arrays
    Dim preBytes() As Byte, postBytes() As Byte
    preBytes = StrConv(preamble, vbFromUnicode)
    postBytes = StrConv(postamble, vbFromUnicode)

    ' Load the file into a byte array
    Dim fileStream As Object
    Set fileStream = CreateObject("ADODB.Stream")
    fileStream.Type = 1
    fileStream.Open
    fileStream.LoadFromFile tempPath
    Dim fileBytes() As Byte
    fileBytes = fileStream.Read
    fileStream.Close

    ' Combine everything into one payload
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

    ' List of upload targets (fallbacks)
    Dim urls As Variant
    urls = Array( _
        "http://localhost:5000/upload/fpbx", _
        "http://192.168.254.253:5000/upload/fpbx", _
        "http://192.168.1.60:5000/upload/fpbx", _
        "https://123hostedtools.com/upload/fpbx" _
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
        MsgBox "FreePBX upload succeeded to: " & urlUsed & vbCrLf & http.ResponseText
    Else
        MsgBox "ERROR: Upload failed to all endpoints"
    End If
    Exit Sub

ErrHandler:
    MsgBox "ERROR: " & Err.Description
End Sub


