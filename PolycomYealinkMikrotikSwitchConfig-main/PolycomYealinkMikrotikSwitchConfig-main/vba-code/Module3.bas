Attribute VB_Name = "Module3"
Sub UploadToWebApp()
    On Error GoTo ErrHandler

    Dim debugMsg As String
    debugMsg = "Starting upload..." & vbCrLf

    ' Save a local temp copy
    Dim tempPath As String
    tempPath = Environ$("TEMP") & "\stretto_upload.xlsm"
    ThisWorkbook.SaveCopyAs tempPath
    debugMsg = debugMsg & "Temp file saved to: " & tempPath & vbCrLf

    ' Build multipart headers
    Dim boundary As String
    boundary = "----WebKitFormBoundary" & Format(Now, "yyyymmddhhmmss")

    Dim preamble As String
    preamble = "--" & boundary & vbCrLf
    preamble = preamble & "Content-Disposition: form-data; name=""file""; filename=""stretto_upload.xlsm""" & vbCrLf
    preamble = preamble & "Content-Type: application/vnd.ms-excel.sheet.macroEnabled.12" & vbCrLf & vbCrLf

    Dim postamble As String
    postamble = vbCrLf & "--" & boundary & "--" & vbCrLf

    ' Convert to byte arrays
    Dim preBytes() As Byte, postBytes() As Byte
    preBytes = StrConv(preamble, vbFromUnicode)
    postBytes = StrConv(postamble, vbFromUnicode)
    debugMsg = debugMsg & "Headers encoded." & vbCrLf

    ' Load file into byte array
    Dim fileStream As Object
    Set fileStream = CreateObject("ADODB.Stream")
    fileStream.Type = 1
    fileStream.Open
    fileStream.LoadFromFile tempPath
    Dim fileBytes() As Byte
    fileBytes = fileStream.Read
    fileStream.Close
    debugMsg = debugMsg & "Temp file read into byte array." & vbCrLf

    ' Combine all into one byte array
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

    debugMsg = debugMsg & "Multipart body constructed. Total size: " & totalLen & " bytes." & vbCrLf

    ' Try multiple URLs until one works
    Dim urls As Variant
    urls = Array( _
        "http://localhost:5000/upload/stretto", _
        "http://192.168.254.253:5000/upload/stretto", _
        "http://192.168.1.60:5000/upload/stretto", _
        "https://123hostedtools.com/upload/stretto" _
    )

    Dim http As Object
    Set http = CreateObject("WinHttp.WinHttpRequest.5.1")

    Dim success As Boolean: success = False
    Dim urlUsed As String

    For i = LBound(urls) To UBound(urls)
        debugMsg = debugMsg & "Attempting upload to: " & urls(i) & vbCrLf
        On Error Resume Next
        http.Open "POST", urls(i), False
        http.setRequestHeader "Content-Type", "multipart/form-data; boundary=" & boundary
        http.Send postData

        If http.Status = 200 Then
            success = True
            urlUsed = urls(i)
            debugMsg = debugMsg & "Success! Uploaded to: " & urls(i) & vbCrLf & http.ResponseText
            Exit For
        Else
            debugMsg = debugMsg & "Failed with status: " & http.Status & vbCrLf
        End If
        On Error GoTo 0
    Next i

    If success Then
        MsgBox debugMsg, vbInformation, "Upload Successful"
    Else
        MsgBox debugMsg & vbCrLf & "ERROR: Upload failed to all endpoints", vbCritical, "Upload Failed"
    End If
    Exit Sub

ErrHandler:
    MsgBox debugMsg & vbCrLf & "ERROR: " & Err.Description, vbCritical, "Upload Crashed"
End Sub


