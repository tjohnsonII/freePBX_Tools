Attribute VB_Name = "Module14"
Sub Fill_Stretto_E_From_vpbx_G()
    Dim wsSrc As Worksheet, wsDst As Worksheet
    Dim lastRow As Long, srcLast As Long, dstLast As Long
    Dim firstDataRow As Long: firstDataRow = 2   ' adjust if your header ends elsewhere

    Set wsSrc = ThisWorkbook.Worksheets("vpbx")
    Set wsDst = ThisWorkbook.Worksheets("stretto_import")

    ' Find how far to copy (max of both sheets' used rows)
    srcLast = wsSrc.Cells(wsSrc.Rows.Count, "G").End(xlUp).row
    dstLast = wsDst.Cells(wsDst.Rows.Count, "E").End(xlUp).row
    lastRow = Application.Max(srcLast, dstLast)
    If lastRow < firstDataRow Then Exit Sub

    Application.ScreenUpdating = False
    ' Copy values only, row-for-row, G -> E
    wsDst.Range("E" & firstDataRow & ":E" & lastRow).Value = _
        wsSrc.Range("G" & firstDataRow & ":G" & lastRow).Value
    Application.ScreenUpdating = True
End Sub


