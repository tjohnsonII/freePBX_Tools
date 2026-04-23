Attribute VB_Name = "Module16"
Sub PopulateFPBXFields()
    Dim ws As Worksheet
    Dim lastRow As Long
    Dim r As Long
    Dim extVal As String
    Dim vmEmail As String
    Dim resp As VbMsgBoxResult
    
    ' 0. safety confirmation
    resp = MsgBox( _
        "Populate fpbx from extensions and overwrite auto-generated columns?" & vbCrLf & vbCrLf & _
        "This will CLEAR and REPOPULATE columns D,E,F,G,H,I,K,L,M,O,P,Q,R,S." & vbCrLf & _
        "It will NOT touch columns A,B,C,J, or N (extension, name, description, voicemail_email, outboundcid)." & vbCrLf & vbCrLf & _
        "Continue?", _
        vbYesNo + vbExclamation + vbDefaultButton2, _
        "Are you sure?")
        
    If resp <> vbYes Then
        Exit Sub
    End If
    
    ' 1. point to the fpbx sheet
    Set ws = ThisWorkbook.Sheets("fpbx")
    
    ' 2. find last used row based on column A (extension)
    lastRow = ws.Cells(ws.Rows.Count, "A").End(xlUp).row
    If lastRow < 2 Then
        MsgBox "No extensions found in column A.", vbInformation, "Nothing to do"
        Exit Sub
    End If
    
    ' 3. clear all the auto-generated columns so we start fresh,
    '    WITHOUT clearing voicemail_email (J) or outboundcid (N)
    Application.ScreenUpdating = False
    
    ws.Range("D2:D" & lastRow).ClearContents  ' tech
    ws.Range("E2:E" & lastRow).ClearContents  ' secret
    ws.Range("F2:F" & lastRow).ClearContents  ' callwaiting_enable
    ws.Range("G2:G" & lastRow).ClearContents  ' voicemail
    ws.Range("H2:H" & lastRow).ClearContents  ' voicemail_enable
    ws.Range("I2:I" & lastRow).ClearContents  ' voicemail_vmpwd
    ' J (voicemail_email) stays
    ws.Range("K2:K" & lastRow).ClearContents  ' voicemail_pager
    ws.Range("L2:L" & lastRow).ClearContents  ' voicemail_options
    ws.Range("M2:M" & lastRow).ClearContents  ' voicemail_same_exten
    ' N (outboundcid) stays
    ws.Range("O2:O" & lastRow).ClearContents  ' id
    ws.Range("P2:P" & lastRow).ClearContents  ' dial
    ws.Range("Q2:Q" & lastRow).ClearContents  ' user
    ws.Range("R2:R" & lastRow).ClearContents  ' max_contacts
    ws.Range("S2:S" & lastRow).ClearContents  ' accountcode
    
    ' 4. loop through each row and repopulate
    For r = 2 To lastRow
        
        extVal = Trim(ws.Cells(r, "A").Value)      ' extension (col A)
        vmEmail = Trim(ws.Cells(r, "J").Value)     ' voicemail_email (col J)
        
        If extVal <> "" Then
        
            ' --- populate computed fields ---
            ws.Cells(r, "D").Value = "pjsip"           ' tech
            ws.Cells(r, "E").Value = "REGEN"           ' secret
            ws.Cells(r, "F").Value = "ENABLED"         ' callwaiting_enable
            ws.Cells(r, "G").Value = "default"         ' voicemail
            ws.Cells(r, "H").Value = "yes"             ' voicemail_enable
            
            ' voicemail_vmpwd = 123 + extension
            ws.Cells(r, "I").Value = "123" & extVal
            
            ' voicemail_email (J) is left as-is
            
            ' voicemail_pager = "off"
            ws.Cells(r, "K").Value = "off"
            
            ' voicemail_options depends on whether vm email is present
            If vmEmail = "" Then
                ws.Cells(r, "L").Value = "attach=no|saycid=no|envelope=no|delete=no"
            Else
                ws.Cells(r, "L").Value = "attach=yes|saycid=no|envelope=no|delete=no"
            End If
            
            ' voicemail_same_exten
            ws.Cells(r, "M").Value = "no"
            
            ' outboundcid (N) stays whatever you entered
            
            ' id = extension
            ws.Cells(r, "O").Value = extVal
            
            ' dial = PJSIP/<ext>
            ws.Cells(r, "P").Value = "PJSIP/" & extVal
            
            ' user = extension
            ws.Cells(r, "Q").Value = extVal
            
            ' max_contacts = 10
            ws.Cells(r, "R").Value = 10
            
            ' accountcode = extension
            ws.Cells(r, "S").Value = extVal
            
        End If
        
    Next r
    
    Application.ScreenUpdating = True
    
    MsgBox "FPBX fields populated." & vbCrLf & _
           "(voicemail_email, outboundcid preserved.)", _
           vbInformation, "Done"
End Sub


