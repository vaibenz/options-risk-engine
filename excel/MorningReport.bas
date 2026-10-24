Attribute VB_Name = "MorningReport"
' Excel side of the risk engine.
'
' BuildMorningReport
'   Reads the csvs that `python -m riskengine.report` writes to out/ and
'   lays them out as a one page report: headline numbers, limit usage
'   (breaches red, warnings amber), greeks by underlying, the spot x vol
'   grid as a heat map and the named stress scenarios.
'
' LoadWhatIfBook
'   Pulls data/sample_book.csv and data/market.csv into a "WhatIf" sheet
'   and writes the greeks as live BS_* formulas (BlackScholes module), so
'   you can change a spot or a vol in the market table and watch the book
'   greeks move without rerunning Python.
'
' Folders: by default the workbook is expected to sit in excel/ next to
' out/ and data/. Put a different repo root in Settings!B1 to override.
Option Explicit

Private Const SHEET_REPORT As String = "Report"
Private Const SHEET_WHATIF As String = "WhatIf"

' ---------------------------------------------------------------- helpers

Private Function Sep() As String
    Sep = Application.PathSeparator
End Function

Private Function RepoRoot() As String
    Dim i As Long, v As String
    For i = 1 To ThisWorkbook.Worksheets.Count
        If ThisWorkbook.Worksheets(i).Name = "Settings" Then
            v = Trim(CStr(ThisWorkbook.Worksheets(i).Range("B1").Value))
        End If
    Next i
    If Len(v) > 0 Then
        RepoRoot = v
    Else
        RepoRoot = ThisWorkbook.Path & Sep() & ".."
    End If
End Function

Private Function LooksNumeric(ByVal s As String) As Boolean
    Dim i As Long, ch As String, digits As Long
    s = Trim(s)
    If Len(s) = 0 Then Exit Function
    For i = 1 To Len(s)
        ch = Mid(s, i, 1)
        If ch Like "#" Then
            digits = digits + 1
        ElseIf InStr("+-.eE", ch) = 0 Then
            Exit Function
        End If
    Next i
    LooksNumeric = digits > 0
End Function

' Reads a simple csv (no quoted commas, which is all pandas writes for
' these files) into a 1 based 2D array of strings. Handles LF or CRLF.
Public Function ReadCsv(ByVal path As String) As Variant
    Dim f As Integer, ln As String, txt As String
    Dim lines() As String, cells() As String
    Dim nR As Long, nC As Long, r As Long, c As Long
    Dim out() As Variant

    If Len(Dir(path)) = 0 Then Err.Raise 53, "ReadCsv", "file not found: " & path
    f = FreeFile
    Open path For Input As #f
    Do While Not EOF(f)
        Line Input #f, ln
        txt = txt & ln & vbLf
    Loop
    Close #f

    txt = Replace(txt, vbCr, "")
    Do While Right(txt, 1) = vbLf
        txt = Left(txt, Len(txt) - 1)
    Loop
    lines = Split(txt, vbLf)
    nR = UBound(lines) - LBound(lines) + 1
    nC = UBound(Split(lines(0), ",")) + 1

    ReDim out(1 To nR, 1 To nC)
    For r = 1 To nR
        cells = Split(lines(r - 1), ",")
        For c = 1 To nC
            If c - 1 <= UBound(cells) Then out(r, c) = cells(c - 1) Else out(r, c) = ""
        Next c
    Next r
    ReadCsv = out
End Function

Private Function CellVal(ByVal s As Variant) As Variant
    If LooksNumeric(CStr(s)) Then
        CellVal = Val(CStr(s))      ' Val always uses "." so this is locale safe
    Else
        CellVal = CStr(s)
    End If
End Function

' Writes a csv array at (row, col), header bold. Returns the next free row.
Private Function PutTable(ws As Worksheet, ByVal row As Long, ByVal col As Long, data As Variant, _
                          Optional ByVal numFmt As String = "#,##0") As Long
    Dim r As Long, c As Long
    For r = 1 To UBound(data, 1)
        For c = 1 To UBound(data, 2)
            With ws.Cells(row + r - 1, col + c - 1)
                ' text stays text, otherwise "-15%" headers get turned into numbers
                If VarType(CellVal(data(r, c))) = vbString Then .NumberFormat = "@"
                .Value = CellVal(data(r, c))
                If r = 1 Then
                    .Font.Bold = True
                    .Interior.Color = RGB(230, 230, 230)
                ElseIf VarType(.Value) = vbDouble Then
                    .NumberFormat = numFmt
                End If
            End With
        Next c
    Next r
    PutTable = row + UBound(data, 1) + 1
End Function

Private Function FindCol(data As Variant, ByVal name As String) As Long
    Dim c As Long
    For c = 1 To UBound(data, 2)
        If LCase(Trim(data(1, c))) = LCase(name) Then
            FindCol = c
            Exit Function
        End If
    Next c
    Err.Raise 9, "FindCol", "column not found: " & name
End Function

Private Function GetSheet(ByVal name As String) As Worksheet
    Dim ws As Worksheet, i As Long
    For i = 1 To ThisWorkbook.Worksheets.Count
        If ThisWorkbook.Worksheets(i).Name = name Then
            Set ws = ThisWorkbook.Worksheets(i)
            Exit For
        End If
    Next i
    If ws Is Nothing Then
        Set ws = ThisWorkbook.Worksheets.Add(After:=ThisWorkbook.Worksheets(ThisWorkbook.Worksheets.Count))
        ws.Name = name
    End If
    ws.Cells.Clear
    Set GetSheet = ws
End Function

Private Function HeatColour(ByVal v As Double, ByVal maxAbs As Double) As Long
    ' white at 0, red for losses, green for gains
    Dim x As Double
    If maxAbs <= 0 Then HeatColour = RGB(255, 255, 255): Exit Function
    x = v / maxAbs
    If x > 1 Then x = 1
    If x < -1 Then x = -1
    If x < 0 Then
        HeatColour = RGB(255, CInt(255 + 120 * x), CInt(255 + 120 * x))
    Else
        HeatColour = RGB(CInt(255 - 120 * x), 255, CInt(255 - 120 * x))
    End If
End Function

' ---------------------------------------------------------------- report

Public Sub BuildMorningReport()
    Dim outDir As String, ws As Worksheet, row As Long
    Dim lim As Variant, und As Variant, grid As Variant, vr As Variant, stress As Variant
    Dim r As Long, c As Long, nBreach As Long, nWarn As Long
    Dim stCol As Long, maxAbs As Double, worst As Double, worstR As Long, worstC As Long
    Dim v As Double

    outDir = RepoRoot() & Sep() & "out" & Sep()
    lim = ReadCsv(outDir & "limits.csv")
    und = ReadCsv(outDir & "by_underlying.csv")
    grid = ReadCsv(outDir & "grid.csv")
    vr = ReadCsv(outDir & "var.csv")
    stress = ReadCsv(outDir & "named_stress.csv")

    Set ws = GetSheet(SHEET_REPORT)

    ws.Cells(1, 1).Value = "Options book risk report (USD)"
    ws.Cells(1, 1).Font.Bold = True
    ws.Cells(1, 1).Font.Size = 14
    ws.Cells(2, 1).Value = "Built " & Format(Now, "yyyy-mm-dd hh:mm") & " from " & outDir

    ' headline
    stCol = FindCol(lim, "status")
    For r = 2 To UBound(lim, 1)
        If lim(r, stCol) = "BREACH" Then nBreach = nBreach + 1
        If lim(r, stCol) = "WARN" Then nWarn = nWarn + 1
    Next r
    worst = 0
    For r = 2 To UBound(grid, 1)
        For c = 2 To UBound(grid, 2)
            v = Val(grid(r, c))
            If Abs(v) > maxAbs Then maxAbs = Abs(v)
            If v < worst Then worst = v: worstR = r: worstC = c
        Next c
    Next r

    row = 4
    ws.Cells(row, 1).Value = "1 day VaR 99% (hist)":   ws.Cells(row, 2).Value = Val(vr(2, 2))
    ws.Cells(row + 1, 1).Value = "1 day ES 99% (hist)": ws.Cells(row + 1, 2).Value = Val(vr(3, 2))
    ws.Cells(row + 2, 1).Value = "Worst grid point":   ws.Cells(row + 2, 2).Value = worst
    If worstR > 0 Then ws.Cells(row + 2, 3).Value = "spot " & grid(1, worstC) & ", vol " & grid(worstR, 1)
    ws.Cells(row + 3, 1).Value = "Limits":             ws.Cells(row + 3, 2).Value = nBreach & " breach, " & nWarn & " warn"
    ws.Range(ws.Cells(row, 2), ws.Cells(row + 2, 2)).NumberFormat = "#,##0"
    ws.Range(ws.Cells(row, 1), ws.Cells(row + 3, 1)).Font.Bold = True
    If nBreach > 0 Then
        ws.Cells(row + 3, 2).Font.Color = RGB(192, 0, 0)
        ws.Cells(row + 3, 2).Font.Bold = True
    End If

    ' limits
    row = row + 5
    ws.Cells(row, 1).Value = "Limit usage": ws.Cells(row, 1).Font.Bold = True
    row = row + 1
    Dim firstLimRow As Long
    firstLimRow = row
    row = PutTable(ws, row, 1, lim)
    For r = 2 To UBound(lim, 1)
        Select Case lim(r, stCol)
            Case "BREACH"
                ws.Range(ws.Cells(firstLimRow + r - 1, 1), ws.Cells(firstLimRow + r - 1, UBound(lim, 2))).Interior.Color = RGB(248, 215, 218)
            Case "WARN"
                ws.Range(ws.Cells(firstLimRow + r - 1, 1), ws.Cells(firstLimRow + r - 1, UBound(lim, 2))).Interior.Color = RGB(255, 243, 205)
        End Select
    Next r
    ws.Range(ws.Cells(firstLimRow + 1, FindCol(lim, "usage_pct")), _
             ws.Cells(firstLimRow + UBound(lim, 1) - 1, FindCol(lim, "usage_pct"))).NumberFormat = "0.0"

    ' greeks
    ws.Cells(row, 1).Value = "Greeks by underlying (delta in index units, rest USD)": ws.Cells(row, 1).Font.Bold = True
    row = PutTable(ws, row + 1, 1, und)

    ' grid as heat map, in USD 000s
    ws.Cells(row, 1).Value = "Spot x vol P&L (USD 000s)": ws.Cells(row, 1).Font.Bold = True
    row = row + 1
    Dim gridRow As Long
    gridRow = row
    row = PutTable(ws, row, 1, grid)
    For r = 2 To UBound(grid, 1)
        For c = 2 To UBound(grid, 2)
            v = Val(grid(r, c))
            With ws.Cells(gridRow + r - 1, c)
                .Value = v / 1000
                .NumberFormat = "#,##0"
                .Interior.Color = HeatColour(v, maxAbs)
            End With
        Next c
    Next r

    ' named stress
    ws.Cells(row, 1).Value = "Named scenarios": ws.Cells(row, 1).Font.Bold = True
    row = PutTable(ws, row + 1, 1, stress)

    ' fixed widths, autofit would size A off the long title in A1
    ws.Columns(1).ColumnWidth = 22
    ws.Range(ws.Columns(2), ws.Columns(10)).ColumnWidth = 12
    ws.Activate
End Sub

' ---------------------------------------------------------------- what if

Public Sub LoadWhatIfBook()
    Dim root As String, ws As Worksheet, book As Variant, mkt As Variant
    Dim r As Long, c As Long, nMkt As Long, mRow As Long, row As Long
    Dim cU As Long, cK As Long, cS As Long, cE As Long, cQ As Long, cM As Long, cV As Long, cId As Long
    Dim mRef As String, kind As String, cp As String

    root = RepoRoot()
    book = ReadCsv(root & Sep() & "data" & Sep() & "sample_book.csv")
    mkt = ReadCsv(root & Sep() & "data" & Sep() & "market.csv")
    Set ws = GetSheet(SHEET_WHATIF)

    ws.Cells(1, 1).Value = "What if: edit spot / vol / valuation date in yellow, greeks recalc live"
    ws.Cells(1, 1).Font.Bold = True
    ws.Cells(2, 1).Value = "Valuation date"
    ws.Cells(2, 2).Value = DateSerial(2026, 10, 23)
    ws.Cells(2, 2).NumberFormat = "yyyy-mm-dd"
    ws.Cells(2, 2).Interior.Color = RGB(255, 242, 204)
    ws.Cells(2, 4).Value = "Vol shift (abs)"
    ws.Cells(2, 5).Value = 0
    ws.Cells(2, 5).Interior.Color = RGB(255, 242, 204)

    ' market table at A4
    mRow = 4
    nMkt = UBound(mkt, 1) - 1
    PutTable ws, mRow, 1, mkt, "0.0000"
    ws.Range(ws.Cells(mRow + 1, 2), ws.Cells(mRow + nMkt, 2)).Interior.Color = RGB(255, 242, 204)
    ws.Range(ws.Cells(mRow + 1, 2), ws.Cells(mRow + nMkt, 2)).NumberFormat = "#,##0.00"

    ' book with formula greeks below
    row = mRow + nMkt + 3
    cId = FindCol(book, "id"): cU = FindCol(book, "underlying"): cK = FindCol(book, "kind")
    cS = FindCol(book, "strike"): cE = FindCol(book, "expiry"): cQ = FindCol(book, "qty")
    cM = FindCol(book, "multiplier"): cV = FindCol(book, "vol")

    Dim hdr As Variant
    hdr = Array("id", "underlying", "kind", "strike", "expiry", "qty", "multiplier", "vol", _
                "T", "price", "delta_1pct_usd", "gamma_1pct_usd", "vega_usd", "theta_usd")
    For c = 0 To UBound(hdr)
        ws.Cells(row, c + 1).Value = hdr(c)
        ws.Cells(row, c + 1).Font.Bold = True
        ws.Cells(row, c + 1).Interior.Color = RGB(230, 230, 230)
    Next c

    Dim first As Long, last As Long, rr As Long
    first = row + 1
    For r = 2 To UBound(book, 1)
        rr = row + r - 1
        ws.Cells(rr, 1).Value = book(r, cId)
        ws.Cells(rr, 2).Value = book(r, cU)
        ws.Cells(rr, 3).Value = book(r, cK)
        ws.Cells(rr, 4).Value = CellVal(book(r, cS))
        If Len(book(r, cE)) > 0 Then
            ws.Cells(rr, 5).Value = DateSerial(Val(Left(book(r, cE), 4)), Val(Mid(book(r, cE), 6, 2)), Val(Mid(book(r, cE), 9, 2)))
            ws.Cells(rr, 5).NumberFormat = "yyyy-mm-dd"
        End If
        ws.Cells(rr, 6).Value = Val(book(r, cQ))
        ws.Cells(rr, 7).Value = Val(book(r, cM))
        ws.Cells(rr, 8).Value = CellVal(book(r, cV))

        ' market row for this underlying
        For c = 2 To UBound(mkt, 1)
            If mkt(c, 1) = book(r, cU) Then mRef = CStr(mRow + c - 1)
        Next c
        Dim S As String, rate As String, dq As String, fx As String, T As String, vol As String, n As String
        S = "$B$" & mRef: rate = "$C$" & mRef: dq = "$D$" & mRef: fx = "$F$" & mRef
        T = "I" & rr
        vol = "MAX(H" & rr & "+$E$2,0.01)"
        n = "F" & rr & "*G" & rr & "*" & fx
        kind = LCase(book(r, cK))
        If kind = "future" Then
            ws.Cells(rr, 9).Value = 0
            ws.Cells(rr, 10).Formula = "=" & S
            ws.Cells(rr, 11).Formula = "=" & n & "*" & S & "/100"
            ws.Range(ws.Cells(rr, 12), ws.Cells(rr, 14)).Value = 0
        Else
            cp = IIf(kind = "call", "C", "P")
            ws.Cells(rr, 9).Formula = "=MAX(E" & rr & "-$B$2,0)/365"
            ws.Cells(rr, 10).Formula = "=BS_PRICE(" & S & ",D" & rr & "," & T & "," & rate & "," & dq & "," & vol & ",""" & cp & """)"
            ws.Cells(rr, 11).Formula = "=BS_DELTA(" & S & ",D" & rr & "," & T & "," & rate & "," & dq & "," & vol & ",""" & cp & """)*" & n & "*" & S & "/100"
            ws.Cells(rr, 12).Formula = "=0.5*BS_GAMMA(" & S & ",D" & rr & "," & T & "," & rate & "," & dq & "," & vol & ")*" & n & "*(0.01*" & S & ")^2"
            ws.Cells(rr, 13).Formula = "=BS_VEGA(" & S & ",D" & rr & "," & T & "," & rate & "," & dq & "," & vol & ")*" & n
            ws.Cells(rr, 14).Formula = "=BS_THETA(" & S & ",D" & rr & "," & T & "," & rate & "," & dq & "," & vol & ",""" & cp & """)*" & n
        End If
    Next r
    last = rr

    ' totals
    ws.Cells(last + 1, 1).Value = "TOTAL"
    ws.Cells(last + 1, 1).Font.Bold = True
    For c = 11 To 14
        ws.Cells(last + 1, c).Formula = "=SUM(" & ws.Cells(first, c).Address(False, False) & ":" & ws.Cells(last, c).Address(False, False) & ")"
        ws.Cells(last + 1, c).Font.Bold = True
    Next c
    ws.Range(ws.Cells(first, 10), ws.Cells(last + 1, 14)).NumberFormat = "#,##0"
    ws.Range(ws.Cells(first, 8), ws.Cells(last, 9)).NumberFormat = "0.000"
    ws.Columns(1).ColumnWidth = 14
    ws.Range(ws.Columns(2), ws.Columns(14)).ColumnWidth = 12
    ws.Activate
End Sub
